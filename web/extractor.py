# -*- coding: utf-8 -*-
"""
Subsistema de Extração e Enriquecimento de Conteúdo Web — Agente Sniper
Extração de texto, parsing de metadados/JSON-LD e enriquecimento concorrente determinístico de fontes.
"""
from __future__ import annotations

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from domain.identity import url_normalizada
from domain.models import Fonte
from domain.normalizer import normalizar, truncar
from web.browser import PersistentPlaywrightManager, _PLAYWRIGHT_MGR, PLAYWRIGHT_ATIVO

logger = logging.getLogger("agente_sniper")

REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "15.0"))
MAX_ENRIQUECIMENTO = int(os.getenv("MAX_ENRIQUECIMENTO", "10"))
ENRICH_MAX_WORKERS = min(16, max(int(os.getenv("ENRICH_MAX_WORKERS", "6")), 2))
MAX_FONTES_FINAIS = int(os.getenv("MAX_FONTES_FINAIS", "40"))
ANO_MINIMO_ATUAL = int(os.getenv("ANO_MINIMO_ATUAL", "2024"))


def extrair_html(
    url: str,
    session: Optional[requests.Session] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Extrai HTML bruto e metadados via requisição HTTP GET síncrona."""
    sess = session or requests.Session()
    req_timeout = timeout if timeout is not None else REQUEST_TIMEOUT
    r = sess.get(
        url,
        headers={"Accept-Language": "pt-BR,pt;q=0.9"},
        timeout=req_timeout,
        allow_redirects=True,
    )
    r.raise_for_status()
    return {"html": r.text, "final_url": r.url, "content_type": r.headers.get("content-type", "")}


def extrair_playwright(
    url: str,
    mgr: Optional[PersistentPlaywrightManager] = None,
    ativo: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    """Extrai conteúdo de página renderizada via Playwright."""
    flag_ativo = PLAYWRIGHT_ATIVO if ativo is None else ativo
    if not flag_ativo:
        return None
    manager = mgr or _PLAYWRIGHT_MGR
    return manager.extrair_pagina_playwright(url, timeout=30000)


def extrair_pagina(
    url: str,
    mgr: Optional[PersistentPlaywrightManager] = None,
    session: Optional[requests.Session] = None,
    ativo_playwright: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Extração resiliente de página com parsing estruturado (meta/JSON-LD) e fallback Playwright.
    """
    flag_pw = PLAYWRIGHT_ATIVO if ativo_playwright is None else ativo_playwright
    try:
        raw = extrair_html(url, session=session)
        ctype = (raw.get("content_type") or "").lower()
        if "html" not in ctype and "xhtml" not in ctype:
            raise RuntimeError("não HTML")
        soup = BeautifulSoup(raw["html"], "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        pub = ""
        for m in soup.find_all("meta"):
            key = normalizar(m.get("property") or m.get("name") or "")
            value = str(m.get("content") or "").strip()
            if key in {"article:published_time", "datepublished", "publish_date", "date"} and value:
                pub = value
                break
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                obj = json.loads(s.get_text(" ", strip=True))
            except Exception:
                continue
            itens = obj if isinstance(obj, list) else [obj]
            stack = list(itens)
            while stack:
                item = stack.pop()
                if isinstance(item, dict):
                    if isinstance(item.get("@graph"), list):
                        stack.extend(item["@graph"])
                    pub = pub or str(item.get("datePublished") or item.get("dateCreated") or "")
                    title = title or str(item.get("headline") or item.get("name") or "")
        for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
            tag.decompose()
        texto = soup.get_text("\n", strip=True)
        texto = re.sub(r"\n{3,}", "\n\n", texto)
        if len(texto) < 250 and flag_pw:
            raise RuntimeError("página quase vazia")
        return {"titulo": title, "conteudo": texto, "data_publicacao": pub, "final_url": raw["final_url"], "direta": True}
    except Exception:
        pw = extrair_playwright(url, mgr=mgr, ativo=flag_pw)
        if pw:
            return {**pw, "direta": True}
        return {"titulo": "", "conteudo": "", "data_publicacao": "", "final_url": url, "direta": False}


def enriquecer(
    fontes: List[Fonte],
    max_enriquecimento: Optional[int] = None,
    max_workers: Optional[int] = None,
    max_fontes_finais: Optional[int] = None,
    mgr: Optional[PersistentPlaywrightManager] = None,
    session: Optional[requests.Session] = None,
    parse_data_fn: Optional[Callable[[str], Any]] = None,
    alias_empresa_fn: Optional[Callable[[str], Optional[str]]] = None,
    cidade_ok_fn: Optional[Callable[[str], bool]] = None,
    estado_ok_fn: Optional[Callable[[str], bool]] = None,
    sinais_fn: Optional[Callable[[str], List[str]]] = None,
    score_fonte_fn: Optional[Callable[[Fonte], float]] = None,
) -> List[Fonte]:
    """
    Executa enriquecimento concorrente das top N fontes com aplicação rigorosamente determinística.
    """
    n_enrich = max_enriquecimento if max_enriquecimento is not None else MAX_ENRIQUECIMENTO
    n_workers = max_workers if max_workers is not None else ENRICH_MAX_WORKERS
    n_finais = max_fontes_finais if max_fontes_finais is not None else MAX_FONTES_FINAIS

    alvo = sorted(fontes, key=lambda x: x.score, reverse=True)[:n_enrich]
    if not alvo:
        return []

    def _exec_enrich_task(item: Tuple[int, str]) -> Tuple[int, Dict[str, Any]]:
        idx, url = item
        logger.info("[EXTRAÇÃO %02d/%02d] %s", idx + 1, len(alvo), url)
        try:
            dados = extrair_pagina(url, mgr=mgr, session=session)
            return idx, dados
        except Exception as e:
            logger.debug("[ENRICH WORKER] %s: %s", url[:80], str(e)[:120])
            return idx, {"titulo": "", "conteudo": "", "data_publicacao": "", "final_url": url, "direta": False}

    tasks = [(i, f.url) for i, f in enumerate(alvo)]
    results_by_idx: Dict[int, Dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="sniper-enrich") as executor:
        future_to_idx = {executor.submit(_exec_enrich_task, t): t[0] for t in tasks}
        for future in concurrent.futures.as_completed(future_to_idx):
            try:
                idx, dados = future.result()
                results_by_idx[idx] = dados
            except Exception as e:
                idx = future_to_idx[future]
                logger.warning("[ENRICH FUTURE] Tarefa %d falhou: %s", idx, str(e)[:120])
                results_by_idx[idx] = {}

    # Aplicação sequencial rigorosamente determinística
    for i, f in enumerate(alvo):
        dados = results_by_idx.get(i, {})
        if not dados.get("conteudo"):
            continue
        old_snippet = f.resumo_busca
        f.titulo = truncar(dados.get("titulo") or f.titulo, 320)
        f.conteudo = truncar(dados.get("conteudo"), 18000)
        f.resumo_busca = old_snippet
        f.direta = bool(dados.get("direta"))
        f.data_publicacao = str(dados.get("data_publicacao") or f.data_publicacao)
        if f.data_publicacao and parse_data_fn:
            d = parse_data_fn(f.data_publicacao)
            if d:
                f.atual = getattr(d, "year", 0) >= ANO_MINIMO_ATUAL
                f.data_tipo = "publicada"
        f.url = url_normalizada(dados.get("final_url") or f.url)
        combined = f.texto()
        if alias_empresa_fn:
            a = alias_empresa_fn(combined)
            if a:
                f.alias_empresa = a
        if cidade_ok_fn:
            f.cidade_confirmada = cidade_ok_fn(combined)
        if estado_ok_fn:
            f.estado_confirmado = estado_ok_fn(combined)
        if f.cidade_confirmada:
            f.escopo = "local"
        elif f.estado_confirmado:
            f.escopo = "nacional"
        if sinais_fn:
            f.sinais = sinais_fn(combined)
        if score_fonte_fn:
            f.score = score_fonte_fn(f)

    for i, f in enumerate(sorted(fontes, key=lambda x: x.score, reverse=True), 1):
        f.id = i
    return sorted(fontes, key=lambda x: x.score, reverse=True)[:n_finais]
