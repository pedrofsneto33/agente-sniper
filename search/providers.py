# -*- coding: utf-8 -*-
"""
Subsistema de Busca e Coleta Web — Agente Sniper
Provedores síncronos e concorrentes (Tavily, DuckDuckGo, Google News RSS) com budget guard, circuit breaker e cache TTL.
"""
from __future__ import annotations

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("agente_sniper")

# ---------- dependências opcionais de busca ----------
try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

try:
    from ddgs import DDGS
except Exception:
    try:
        from duckduckgo_search import DDGS
    except Exception:
        DDGS = None

# ---------- constantes de configuração ----------
MAX_TAVILY_QUERIES_PER_RUN = int(os.getenv("MAX_TAVILY_QUERIES_PER_RUN", "25"))
_TAVILY_CACHE_TTL = 86400.0  # 24h
USAR_TAVILY = os.getenv("USAR_TAVILY", "1") == "1"
USAR_DDG = os.getenv("USAR_DDG", "1") == "1"
USAR_NEWS_RSS = os.getenv("USAR_NEWS_RSS", "1") == "1"
DISCOVERY_MAX_WORKERS = min(32, max(int(os.getenv("DISCOVERY_MAX_WORKERS", "16")), 16))


class TavilyBudgetGuard:
    """Gerencia o orçamento rígido, cache em memória/TTL e Circuit Breaker do Tavily."""

    def __init__(self, max_queries: int = MAX_TAVILY_QUERIES_PER_RUN):
        self.max_queries = max_queries
        self._lock = threading.Lock()
        self.circuit_open = False
        self.circuit_reason = ""
        self._cache: Dict[str, Tuple[List[Dict[str, Any]], float]] = {}

        # Telemetria
        self.queries_attempted = 0
        self.queries_executed = 0
        self.queries_blocked_budget = 0
        self.cache_hits = 0
        self.failures = 0

    @property
    def estimated_credits_used(self) -> int:
        return self.queries_executed

    def search(self, client: Any, query: str, categoria: str) -> List[Dict[str, Any]]:
        """Executa busca no Tavily com controle atômico de orçamento, cache e circuit breaker."""
        if not client or not (os.getenv("USAR_TAVILY", "1") == "1"):
            return []

        q_key = query.strip().lower()

        with self._lock:
            self.queries_attempted += 1

            # 1. Circuit Breaker
            if self.circuit_open:
                return []

            # 2. Cache por TTL (24h)
            if q_key in self._cache:
                results, ts = self._cache[q_key]
                if time.time() - ts < _TAVILY_CACHE_TTL:
                    self.cache_hits += 1
                    return results

            # 3. Budget Guard (Máximo de consultas por RUN)
            if self.queries_executed >= self.max_queries:
                self.queries_blocked_budget += 1
                logger.info("[TAVILY BUDGET] Limite de %d consultas atingido. Query pulada: %s", self.max_queries, query[:60])
                return []

            # Reserva o slot de execução
            self.queries_executed += 1

        # Execução fora do lock
        try:
            r = client.search(query=query, max_results=5, search_depth="basic", include_answer=False)
            res = [
                {
                    "titulo": x.get("title", ""),
                    "url": x.get("url", ""),
                    "conteudo": x.get("content", ""),
                    "origem": "Tavily",
                    "data_publicacao": x.get("published_date", "") or "",
                    "categoria": categoria,
                }
                for x in r.get("results", [])
            ]
            with self._lock:
                self._cache[q_key] = (res, time.time())
            return res
        except Exception as e:
            err_msg = str(e)
            with self._lock:
                self.failures += 1
                err_lower = err_msg.lower()
                if any(k in err_lower for k in ["429", "quota", "rate limit", "credits", "unauthorized", "401", "forbidden", "403"]):
                    self.circuit_open = True
                    self.circuit_reason = err_msg[:120]
                    logger.warning("[TAVILY CIRCUIT BREAKER ABERTO] %s. Tavily desativado para esta run.", self.circuit_reason)
                else:
                    logger.warning("[TAVILY] %s", err_msg[:160])
            return []


_TAVILY_GUARD = TavilyBudgetGuard()


def buscar_tavily(
    client: Any,
    query: str,
    categoria: str,
    guard: Optional[TavilyBudgetGuard] = None,
) -> List[Dict[str, Any]]:
    """Executa busca via Tavily com o guardião de budget e cache."""
    g = guard or _TAVILY_GUARD
    return g.search(client, query, categoria)


def buscar_ddg(query: str, categoria: str) -> List[Dict[str, Any]]:
    """Executa busca regional via DuckDuckGo com tratamento de falhas."""
    if not DDGS or not (os.getenv("USAR_DDG", "1") == "1"):
        return []
    try:
        with DDGS() as ddgs:
            r = list(ddgs.text(query, region="br-pt", max_results=7))
        if not r:
            logger.info("[DDG] 0 resultados | %s", query[:100])
            return []
        return [
            {
                "titulo": x.get("title", ""),
                "url": x.get("href", ""),
                "conteudo": x.get("body", ""),
                "origem": "DuckDuckGo",
                "data_publicacao": "",
                "categoria": categoria,
            }
            for x in r
        ]
    except Exception as e:
        logger.warning("[DDG] %s", str(e)[:160])
        return []


def buscar_news_rss(
    query: str,
    categoria: str,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, Any]]:
    """Executa busca de notícias recentes via Google News RSS Feed."""
    if not (os.getenv("USAR_NEWS_RSS", "1") == "1"):
        return []
    try:
        url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        sess = session or requests.Session()
        r = sess.get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "xml")
        out = []
        for item in soup.find_all("item")[:10]:
            def txt(tag_name: str) -> str:
                tag = item.find(tag_name)
                return tag.get_text(" ", strip=True) if tag else ""
            description_html = txt("description")
            out.append({
                "titulo": txt("title"),
                "url": txt("link"),
                "conteudo": BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True),
                "origem": "Google News RSS",
                "data_publicacao": txt("pubDate"),
                "categoria": categoria,
            })
        return out
    except Exception as e:
        logger.warning("[NEWS RSS] %s", str(e)[:160])
        return []


def gerar_consultas(
    empresa_alvo: Optional[str] = None,
    cidade: Optional[str] = None,
    estado: Optional[str] = None,
    nicho: Optional[str] = None,
    concorrentes: Optional[List[str]] = None,
    queries_nicho: Optional[List[str]] = None,
    ano: Optional[int] = None,
) -> Dict[str, List[Tuple[str, str]]]:
    """
    Gera a matriz multi-nicho de consultas estruturadas para descoberta competitiva.
    """
    emp_nome = empresa_alvo or os.getenv("EMPRESA_ALVO", "Supermercado Carvalho").strip()
    cid = cidade if cidade is not None else os.getenv("CIDADE", "Teresina").strip()
    n = nicho if nicho is not None else os.getenv("NICHO", "supermercado").strip().lower()
    concs = concorrentes if concorrentes is not None else [x.strip() for x in os.getenv("CONCORRENTES", "").split("|") if x.strip()]
    q_nicho = queries_nicho if queries_nicho is not None else [
        "preço", "ofertas", "encarte", "promoção", "reclamação", "expansão", "inauguração", "vagas", "trabalhe conosco"
    ]
    cur_year = ano or time.localtime().tm_year

    emp = f'"{emp_nome}"'
    local = f'"{cid}"' if cid else ""
    empresa = []
    for q in q_nicho:
        empresa.append((f"{emp} {local} {q} {cur_year}".strip(), emp_nome))
    empresa.extend([
        (f"{emp} {local} notícias {cur_year}".strip(), emp_nome),
        (f"{emp} {local} expansão concorrentes mercado {cur_year}".strip(), emp_nome),
    ])
    mercado = [
        (f"{n} {local} mercado tendências preço comportamento {cur_year}".strip(), "mercado"),
        (f"{n} Brasil tendências {cur_year}".strip(), "mercado"),
    ]
    concorrencia = []
    comercial = [
        (f'{emp} {local} comprar online loja virtual catalogo produtos preços ofertas {cur_year}'.strip(), emp_nome),
        (f'{emp} {local} site oficial supershop loja compras {cur_year}'.strip(), emp_nome),
    ]
    for nome in concs:
        concorrencia.extend([
            (f'"{nome}" {local} preço promoção expansão notícias {cur_year}'.strip(), nome),
            (f'"{nome}" {local} reclamação atendimento avaliação {cur_year}'.strip(), nome),
            (f'"{nome}" {local} aplicativo delivery marketing {cur_year}'.strip(), nome),
        ])
        comercial.extend([
            (f'"{nome}" {local} comprar online loja virtual catalogo produtos preços ofertas {cur_year}'.strip(), nome),
            (f'"{nome}" {local} site oficial loja compras catálogo {cur_year}'.strip(), nome),
        ])
    return {"empresa": empresa, "concorrencia": concorrencia, "comercial": comercial, "mercado": mercado}


def coletar_tudo(
    tavily_client: Any = None,
    consultas: Optional[Dict[str, List[Tuple[str, str]]]] = None,
    max_consultas_por_grupo: Optional[int] = None,
    usar_tavily: Optional[bool] = None,
    usar_ddg: Optional[bool] = None,
    usar_news_rss: Optional[bool] = None,
    max_workers: Optional[int] = None,
    guard: Optional[TavilyBudgetGuard] = None,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, Any]]:
    """
    Executa busca concorrente multi-provedor com agregação determinística preservada por query_id.
    """
    consultas_map = consultas if consultas is not None else gerar_consultas()
    todas: List[Dict[str, Any]] = []
    max_por_grupo = max_consultas_por_grupo if max_consultas_por_grupo is not None else int(os.getenv("MAX_CONSULTAS_POR_GRUPO", "5"))
    flag_tavily = (os.getenv("USAR_TAVILY", "1") == "1") if usar_tavily is None else usar_tavily
    flag_ddg = (os.getenv("USAR_DDG", "1") == "1") if usar_ddg is None else usar_ddg
    flag_rss = (os.getenv("USAR_NEWS_RSS", "1") == "1") if usar_news_rss is None else usar_news_rss
    workers = max_workers if max_workers is not None else min(32, max(int(os.getenv("DISCOVERY_MAX_WORKERS", "16")), 16))
    t_guard = guard or _TAVILY_GUARD

    flat_tasks: List[Tuple[int, str, str, str, str]] = []
    q_id = 0
    for grupo, itens in consultas_map.items():
        itens_exec = itens[:max_por_grupo]
        logger.info("[COLETA] %s | %d consultas", grupo, len(itens_exec))
        for q, alvo in itens_exec:
            if flag_tavily and tavily_client:
                flat_tasks.append((q_id, "tavily", grupo, q, alvo))
            if flag_ddg:
                flat_tasks.append((q_id, "ddg", grupo, q, alvo))
            if flag_rss:
                flat_tasks.append((q_id, "news_rss", grupo, q, alvo))
            q_id += 1

    def _exec_provider_task(task: Tuple[int, str, str, str, str]) -> Tuple[int, str, List[Dict[str, Any]]]:
        qid, prov, grupo, q, alvo = task
        resultados = []
        try:
            if prov == "tavily" and tavily_client:
                resultados = buscar_tavily(tavily_client, q, grupo, guard=t_guard)
            elif prov == "ddg":
                resultados = buscar_ddg(q, grupo)
            elif prov == "news_rss":
                resultados = buscar_news_rss(q, grupo, session=session)
            for r in resultados:
                r["alvo"] = alvo
        except Exception as e:
            logger.warning("[DISCOVERY WORKER %s] %s | %s: %s", prov.upper(), grupo, q[:60], str(e)[:120])
        return qid, prov, resultados

    results_by_qid: Dict[int, Dict[str, List[Dict[str, Any]]]] = {
        i: {"tavily": [], "ddg": [], "news_rss": []} for i in range(q_id)
    }

    if flat_tasks:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sniper-discovery") as executor:
            future_map = {executor.submit(_exec_provider_task, t): t for t in flat_tasks}
            for future in concurrent.futures.as_completed(future_map):
                try:
                    qid, prov, res = future.result()
                    results_by_qid[qid][prov] = res
                except Exception as e:
                    task_info = future_map[future]
                    logger.warning("[DISCOVERY FUTURE] Tarefa %s falhou: %s", str(task_info[:2]), str(e)[:120])

    # Reconstituição rigorosamente determinística na ordem canônica (query_id -> tavily -> ddg -> news_rss)
    for i in range(q_id):
        todas.extend(results_by_qid[i]["tavily"])
        todas.extend(results_by_qid[i]["ddg"])
        todas.extend(results_by_qid[i]["news_rss"])

    return todas
