# -*- coding: utf-8 -*-
"""
AGENTE SNIPER v11.8.0
Motor genérico de inteligência competitiva com memória histórica.

OBJETIVO
--------
Transformar dados públicos da web em:
  evidência -> eventos -> sinais -> decisão -> alertas.

O nicho é configurável. Supermercado é apenas um perfil de pesquisa.
Perfis prontos: supermercado, restaurante, clínica, hotel, farmácia,
imobiliária, tecnologia/SaaS, educação, varejo, serviços e genérico.

ARQUITETURA
-----------
1. Configuração genérica + perfil de nicho
2. Busca multicanal gratuita/baixo custo: Tavily opcional, DDGS, Google News RSS
3. Extração direta por requests/BeautifulSoup; Playwright opcional para JS
4. Validação de identidade, localidade, data e qualidade
5. Deduplicação + fingerprints
6. Memória SQLite para comparar execuções
7. Detecção determinística de eventos e sinais
8. LLM opcional para interpretação estruturada (Ollama local -> Gemini -> Groq)
9. Validação de referências e IDs de evidência
10. Dashboard HTML executivo + PDF executivo + JSON/CSV auditáveis

INSTALAÇÃO
-----------
pip install -r requirements_sniper_v11_5_1.txt

Opcional:
  playwright install chromium
  Ollama local em http://localhost:11434

ENV MÍNIMO
----------
EMPRESA_ALVO=Supermercado Carvalho
CIDADE=Teresina
ESTADO=PI
NICHO=supermercado

Pelo menos um mecanismo de IA é recomendado, mas NÃO obrigatório:
OLLAMA_URL=http://localhost:11434
OLLAMA_MODELO=gemma3:4b
GEMINI_API_KEY=...
CHAVE_GROQ=...
CHAVE_TAVILY=...

Observação:
- Modelos via API podem ter limites e mudar ao longo do tempo.
- O núcleo continua funcional sem LLM.
"""

from __future__ import annotations

import concurrent.futures
import csv
import difflib
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from html import unescape as html_unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import quote_plus, urljoin, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from domain.models import Fonte, PriceItem
from domain.normalizer import (
    normalizar,
    remover_acentos,
    termo,
    truncar,
    parse_data,
    parse_money,
    normalizar_quantidade,
    nome_produto_normalizado,
    tokens_produto,
    score_clamp,
)
from domain.identity import (
    sha1,
    url_normalizada,
    dominio,
    data_na_url,
    data_publicacao,
    cidade_ok as _domain_cidade_ok,
    estado_ok as _domain_estado_ok,
    identidade_conflitante as _domain_identidade_conflitante,
)
from domain.matching import similaridade_produto
from domain.events import (
    EVENT_RULES,
    RISK_KINDS,
    OPPORTUNITY_KINDS,
    recencia_score,
    qualidade_fonte,
    evento_titulo_estavel,
    canonical_event_key,
    _primary_event_kind as _domain_primary_event_kind,
    eventos_sao_mesmo_fato,
    criar_eventos as _domain_criar_eventos,
)
from domain.scoring import (
    medir_dimensoes,
    score_ambiente_competitivo,
    score_pressao_competitiva as _domain_score_pressao_competitiva,
    score_vulnerabilidade_empresa as _domain_score_vulnerabilidade_empresa,
    classificar_sinal,
    acao_evento,
    gerar_sinais_deterministicos,
    score_momentum,
)
from domain.decision import (
    inteligencia_deterministica,
    validar_ids_sinais,
    validar_pacote,
)
from domain.profiles import (
    NICHE_PROFILES,
    obter_perfil_nicho,
)
from domain.sources import (
    DOMINIOS_PRIORITARIOS,
    CIDADES_EXTERIORES,
    dominios_oficiais_configurados,
    score_fonte,
    classificar_escopo,
    sinais_deterministicos,
    transformar,
    deduplicar,
)
from reports import (
    ref_text,
    fonte_por_id,
    html_escape,
    rotulo_dimensao,
    gerar_html as _reports_gerar_html,
    gerar_pdf as _reports_gerar_pdf,
    salvar_json as _reports_salvar_json,
    salvar_csv_fontes as _reports_salvar_csv_fontes,
)
from llm import (
    json_seguro,
    build_system_prompt,
    chamar_ollama,
    chamar_gemini,
    chamar_groq,
    chamar_llm_json,
    gerar_inteligencia_llm as _llm_gerar_inteligencia_llm,
    CACHE,
    CACHE_TTL,
)
from storage.sqlite import MemoriaSniper as _StorageMemoriaSniper
from search import (
    TavilyBudgetGuard,
    buscar_ddg,
    buscar_news_rss as _search_buscar_news_rss,
    buscar_tavily as _search_buscar_tavily,
    gerar_consultas as _search_gerar_consultas,
)
from web import (
    PersistentPlaywrightManager,
    extrair_html as _web_extrair_html,
    extrair_pagina as _web_extrair_pagina,
    extrair_playwright as _web_extrair_playwright,
)
from pipeline import (
    OfflineNetworkGuard,
    resolver_fixture_fontes_offline,
    executar_replay_offline,
    coletar_tudo,
    enriquecer,
)
from pricing import (
    MONEY_RE,
    PRICE_SOURCES,
    PRICE_PRODUCT_SCHEMA_TYPES,
    PRICE_BLOCKED_DOMAINS,
    PRICE_NONCOMMERCIAL_URL_HINTS,
    PRICE_NEGATIVE_PATH_HINTS,
    PRICE_PAGE_NEGATIVE_TERMS,
    PRICE_COMMERCIAL_CONTENT_HINTS,
    PRICE_DISCOVERY_PATH_HINTS,
    get_http_session,
    _is_non_commercial_url,
    _price_page_type,
    _is_blocked_price_domain,
    is_price_candidate_url,
    _commercial_signal_url,
    carregar_price_sources,
    _fetch_html_http,
    _extract_commercial_links,
    _expand_commercial_domain,
    _discover_official_commercial_urls,
    descobrir_fontes_preco,
    mesclar_price_sources,
    _walk_json,
    _extract_price_from_obj,
    _schema_types,
    _plausible_price,
    _price_item_confidence,
    _extract_product_objects,
    _price_page_html,
    _buscar_preco_site,
    coletar_itens_preco_fonte,
    _playwright_session_search,
    comparar_precos,
)

# ---------- dependências opcionais ----------
try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

try:
    from dateutil import parser as date_parser
except Exception:
    date_parser = None

try:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
except Exception:
    FPDF = None
    XPos = YPos = None

# ============================================================
# 0. CONFIGURAÇÃO
# ============================================================

load_dotenv()

APP_VERSION = "11.8.0"
HOJE = datetime.now()
RUN_ID = HOJE.strftime("%Y%m%d_%H%M%S")
SEMANA_ID = HOJE.strftime("%Y-W%U")

EMPRESA_ALVO = os.getenv("EMPRESA_ALVO", "Supermercado Carvalho").strip()
EMPRESA_URL = os.getenv("EMPRESA_URL", "").strip()
CIDADE = os.getenv("CIDADE", "Teresina").strip()
ESTADO = os.getenv("ESTADO", "PI").strip()
NICHO = os.getenv("NICHO", "supermercado").strip().lower()

TERMOS_CONFLITANTES_IDENTIDADE_ENV = os.getenv("TERMOS_CONFLITANTES_IDENTIDADE", "").strip()
TERMOS_CONFLITANTES_IDENTIDADE = [
    x.strip() for x in TERMOS_CONFLITANTES_IDENTIDADE_ENV.split(",") if x.strip()
] if TERMOS_CONFLITANTES_IDENTIDADE_ENV else None

ALIASES_ENV = os.getenv("EMPRESA_ALIASES", "").strip()
if ALIASES_ENV:
    EMPRESA_ALIASES = [x.strip() for x in ALIASES_ENV.split("|") if x.strip()]
else:
    EMPRESA_ALIASES = [EMPRESA_ALVO]

CONCORRENTES = [x.strip() for x in os.getenv("CONCORRENTES", "").split("|") if x.strip()]

PASTA_RESULTADOS = Path(os.getenv("PASTA_RESULTADOS", "sniper_resultados"))
PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
PASTA_EXECUCAO = PASTA_RESULTADOS / RUN_ID
PASTA_EXECUCAO.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("SNIPER_DB", str(PASTA_RESULTADOS / "sniper_historico.sqlite3")))

JANELA_DIAS = int(os.getenv("JANELA_DIAS", "90"))
ANO_MINIMO_ATUAL = int(os.getenv("ANO_MINIMO_ATUAL", str(max(2025, HOJE.year - 1))))
ANO_MINIMO_HISTORICO = int(os.getenv("ANO_MINIMO_HISTORICO", "2020"))
MAX_FONTES_FINAIS = int(os.getenv("MAX_FONTES_FINAIS", "80"))
MAX_ENRIQUECIMENTO = min(int(os.getenv("MAX_ENRIQUECIMENTO", "16")), 16)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "18"))
PLAYWRIGHT_ATIVO = os.getenv("USAR_PLAYWRIGHT", "0") == "1"

# Monitor de preços: opcional e genérico. Para e-commerce dinâmico, usa Playwright
# determinístico quando disponível; nunca usa LLM para navegar ou extrair preços.
MONITORAR_PRECOS = os.getenv("USAR_MONITOR_PRECOS", "1") == "1"
PRECO_USAR_PLAYWRIGHT = os.getenv("PRECO_USAR_PLAYWRIGHT", "1") == "1"
MAX_PRECO_ITENS = int(os.getenv("MAX_PRECO_ITENS", "15"))
MAX_BUSCAS_PRECO_CONCORRENTE = int(os.getenv("MAX_BUSCAS_PRECO_CONCORRENTE", "15"))
PRECO_MIN_SIMILARIDADE = float(os.getenv("PRECO_MIN_SIMILARIDADE", "0.72"))
PRECO_MAX_RESULTADOS_POR_BUSCA = int(os.getenv("PRECO_MAX_RESULTADOS_POR_BUSCA", "8"))
PRECO_MAX_OCR_ITENS_POR_PAGINA = min(int(os.getenv("PRECO_MAX_OCR_ITENS_POR_PAGINA", "50")), 100)
EXTRACTION_ENGINE = os.getenv("EXTRACTION_ENGINE", "generic").strip().lower()

# JSON opcional para qualquer nicho. Exemplo:
# PRICE_SOURCES_JSON=[{"name":"Carvalho","role":"target","url":"..."},{"name":"Concorrente","role":"competitor","url":"...","search_url":"https://site/catalogo?q={query}"}]
PRECO_SOURCES_JSON = os.getenv("PRICE_SOURCES_JSON", "").strip()
PRECO_ALVO_URLS = [x.strip() for x in os.getenv("PRECO_ALVO_URLS", "").split("|") if x.strip()]
PRICE_SITE_DISCOVERY = os.getenv("PRICE_SITE_DISCOVERY", "1") == "1"
PRICE_DISCOVERY_LIMIT_PER_ENTITY = min(int(os.getenv("PRICE_DISCOVERY_LIMIT_PER_ENTITY", "4")), 4)
PRICE_CRAWL_LINK_LIMIT = min(int(os.getenv("PRICE_CRAWL_LINK_LIMIT", "20")), 20)
PRICE_MAX_DOMAINS_PER_ENTITY = int(os.getenv("PRICE_MAX_DOMAINS_PER_ENTITY", "4"))
PRICE_REQUIRE_COMMERCIAL_SIGNAL = os.getenv("PRICE_REQUIRE_COMMERCIAL_SIGNAL", "1") == "1"
SITEMAP_PROBING_TIMEOUT = float(os.getenv("SITEMAP_PROBING_TIMEOUT", "4.0"))
DISCOVERY_MAX_WORKERS = min(int(os.getenv("DISCOVERY_MAX_WORKERS", "6")), 10)
ENRICH_MAX_WORKERS = min(int(os.getenv("ENRICH_MAX_WORKERS", "8")), 12)
PRICE_HISTORY_MIN_CHANGE_PCT = float(os.getenv("PRICE_HISTORY_MIN_CHANGE_PCT", "0.5"))
# v11.8
EVENT_DATE_CLUSTER_DAYS = int(os.getenv("EVENT_DATE_CLUSTER_DAYS", "45"))
EVENT_TITLE_SIM_THRESHOLD = float(os.getenv("EVENT_TITLE_SIM_THRESHOLD", "0.52"))
EVENT_TOKEN_SIM_THRESHOLD = float(os.getenv("EVENT_TOKEN_SIM_THRESHOLD", "0.30"))
EVENT_CURRENT_WINDOW_DAYS = int(os.getenv("EVENT_CURRENT_WINDOW_DAYS", str(JANELA_DIAS)))
EVENT_CONTEXTUAL_MAX_DAYS = int(os.getenv("EVENT_CONTEXTUAL_MAX_DAYS", "365"))

PRICE_AUTO_SEARCH_COMMERCIAL = os.getenv("PRICE_AUTO_SEARCH_COMMERCIAL", "1") == "1"
PRICE_COMMERCIAL_QUERY_LIMIT = int(os.getenv("PRICE_COMMERCIAL_QUERY_LIMIT", "3"))
PRICE_PLAYWRIGHT_TIMEOUT = min(int(os.getenv("PRICE_PLAYWRIGHT_TIMEOUT", "10000")), 10000)
PRICE_MAX_HTTP_FETCHES = min(int(os.getenv("PRICE_MAX_HTTP_FETCHES", "30")), 30)
_PRICE_HTTP_CACHE: Dict[str, Tuple[str, str, float]] = {}
_PRICE_FETCH_COUNT = 0

USAR_TAVILY = os.getenv("USAR_TAVILY", "1") == "1"
USAR_DDG = os.getenv("USAR_DDG", "1") == "1"
USAR_NEWS_RSS = os.getenv("USAR_GOOGLE_NEWS_RSS", "1") == "1"

CHAVE_TAVILY = os.getenv("CHAVE_TAVILY", "").strip()
CHAVE_GROQ = os.getenv("CHAVE_GROQ", "").strip()
USAR_GROQ = os.getenv("USAR_GROQ", "0") == "1"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
OLLAMA_MODELO = os.getenv("OLLAMA_MODELO", "gemma3:4b").strip()

GROQ_MODELOS = [
    x.strip() for x in os.getenv(
        "GROQ_MODELOS",
        "openai/gpt-oss-20b|llama-3.3-70b-versatile|llama-3.1-8b-instant"
    ).split("|") if x.strip()
]
GEMINI_MODELOS = [
    x.strip() for x in os.getenv(
        "GEMINI_MODELOS",
        "gemini-3.1-flash-lite|gemini-3.5-flash-lite|gemini-2.5-flash-lite"
    ).split("|") if x.strip()
]

# ============================================================
# 1. LOG
# ============================================================

logger = logging.getLogger("sniper_v11")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(PASTA_RESULTADOS / "agente_sniper_v11.log", encoding="utf-8")
    sh = logging.StreamHandler(sys.stdout)
    fh.setFormatter(formatter)
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0 Safari/537.36 AgenteSniper/11.8.0"
)

# ============================================================
# 2. PERFIS DE NICHO (DOMAIN BINDINGS)
# ============================================================

PROFILE = obter_perfil_nicho(NICHO)

# ============================================================
# 3. HELPERS & ADAPTERS (DOMAIN BINDINGS)
# ============================================================

def alias_empresa(texto: str) -> Optional[str]:
    """Identidade conservadora; sobrenome isolado não é alias automático."""
    candidatos = [x.strip() for x in EMPRESA_ALIASES if x.strip()]
    partes = [x for x in re.split(r"\s+", normalizar(EMPRESA_ALVO)) if len(x) >= 4]
    if len(partes) >= 2:
        candidatos.append(" ".join(partes))
    for a in sorted(set(candidatos), key=len, reverse=True):
        if termo(texto, a):
            return a
    return None


def identidade_conflitante(texto: str, empresa_alvo: str = EMPRESA_ALVO, termos_conflitantes: Optional[Sequence[str]] = None) -> bool:
    if termos_conflitantes is None:
        termos_conflitantes = TERMOS_CONFLITANTES_IDENTIDADE
    return _domain_identidade_conflitante(texto, empresa_alvo=empresa_alvo, termos_conflitantes=termos_conflitantes)


def cidade_ok(texto: str, cidade: str = CIDADE) -> bool:
    return _domain_cidade_ok(texto, cidade)


def estado_ok(texto: str, estado: str = ESTADO) -> bool:
    return _domain_estado_ok(texto, estado)


def source_domain_root(url: str) -> str:
    return dominio(url)

# ============================================================
# FASE 18.1: POOL DE CONEXÕES HTTP E CACHE DE PROBING
# ============================================================

_HTTP_SESSION: Optional[requests.Session] = None

def get_http_session() -> requests.Session:
    """Retorna ou inicializa uma Session HTTP reutilizável com pooling de conexões e keep-alive."""
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=25,
            pool_maxsize=25,
            max_retries=Retry(
                total=1,
                backoff_factor=0.2,
                status_forcelist=[502, 503, 504],
                raise_on_status=False,
            )
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        _HTTP_SESSION = session
    return _HTTP_SESSION

_STATS_LOCK = threading.Lock()

_IO_STATS: Dict[str, Any] = {
    "domain_probes": 0,
    "probes_cache_hit": 0,
    "sitemaps_skipped": 0,
    "http_requests": 0,
    "http_time": 0.0,
    "expansion_time": 0.0,
    "unique_domains": set(),
    "repeated_domains": 0,
    "discovery_time": 0.0,
    "discovery_workers": DISCOVERY_MAX_WORKERS,
    "discovery_tasks": 0,
    "enrich_time": 0.0,
    "enrich_workers": ENRICH_MAX_WORKERS,
    "enrich_tasks": 0,
    "http_200": 0,
    "http_403": 0,
    "http_429": 0,
    "http_5xx": 0,
    "http_timeouts": 0,
    "host_errors": {},
}

_DOMAIN_EXPANSION_CACHE: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
_SITEMAP_DEAD_DOMAINS: Set[str] = set()

# ============================================================
# FASE 18.3: PLAYWRIGHT PERSISTENTE (WEB BINDINGS)
# ============================================================

_PLAYWRIGHT_MGR = PersistentPlaywrightManager(ativo=PLAYWRIGHT_ATIVO)

# ============================================================
# FASE 19: TAVILY BUDGET GUARD & CIRCUIT BREAKER (SEARCH BINDINGS)
# ============================================================

MAX_TAVILY_QUERIES_PER_RUN = min(int(os.getenv("MAX_TAVILY_QUERIES_PER_RUN", "5")), 5)
_TAVILY_CACHE_TTL = 86400.0  # 24h

_TAVILY_GUARD = TavilyBudgetGuard(max_queries=MAX_TAVILY_QUERIES_PER_RUN)

# ============================================================
# 5. BUSCAS (SEARCH BINDINGS)
# ============================================================

def gerar_consultas(**kwargs: Any) -> Dict[str, List[Tuple[str, str]]]:
    kwargs.setdefault("empresa_alvo", EMPRESA_ALVO)
    kwargs.setdefault("cidade", CIDADE)
    kwargs.setdefault("estado", ESTADO)
    kwargs.setdefault("nicho", NICHO)
    kwargs.setdefault("concorrentes", CONCORRENTES)
    kwargs.setdefault("queries_nicho", PROFILE.get("queries") if isinstance(PROFILE, dict) else None)
    kwargs.setdefault("ano", HOJE.year)
    return _search_gerar_consultas(**kwargs)


def buscar_tavily(client: Any, query: str, categoria: str) -> List[Dict[str, Any]]:
    return _search_buscar_tavily(client, query, categoria, guard=_TAVILY_GUARD)


def buscar_news_rss(query: str, categoria: str) -> List[Dict[str, Any]]:
    return _search_buscar_news_rss(query, categoria, session=get_http_session())


# (coletar_tudo reexportado diretamente do pacote pipeline)

# ============================================================
# 6. VALIDAÇÃO / NORMALIZAÇÃO DAS FONTES (DOMAIN SOURCES BINDINGS)
# ============================================================
# Reexportados diretamente de domain.sources:
# dominios_oficiais_configurados, score_fonte, classificar_escopo,
# sinais_deterministicos, transformar, deduplicar, DOMINIOS_PRIORITARIOS, CIDADES_EXTERIORES

# ============================================================
# 7. EXTRAÇÃO DIRETA (WEB EXTRACTION BINDINGS)
# ============================================================

def extrair_html(url: str) -> Dict[str, Any]:
    return _web_extrair_html(url, session=get_http_session(), timeout=REQUEST_TIMEOUT)


def extrair_playwright(url: str) -> Optional[Dict[str, Any]]:
    return _web_extrair_playwright(url, mgr=_PLAYWRIGHT_MGR)


def extrair_pagina(url: str) -> Dict[str, Any]:
    return _web_extrair_pagina(url, mgr=_PLAYWRIGHT_MGR, session=get_http_session())


# (enriquecer reexportado diretamente do pacote pipeline)

# ============================================================
# 8. MONITORAMENTO DE PREÇOS E PROMOÇÕES (PRICING BINDINGS)
# ============================================================
# Símbolos e delegatórios reexportados do pacote pricing:
# (MONEY_RE, _walk_json, _extract_price_from_obj, _schema_types,
#  _plausible_price, _price_item_confidence, _extract_product_objects,
#  _price_page_html, _buscar_preco_site, coletar_itens_preco_fonte,
#  _playwright_session_search, comparar_precos)

# ============================================================
# 8. MEMÓRIA HISTÓRICA SQLITE
# ============================================================

class MemoriaSniper(_StorageMemoriaSniper):
    """Adapter de compatibilidade para vincular constantes de ambiente globais."""

    def save_run(
        self,
        run_id: str,
        fontes: Sequence[Fonte],
        events: Sequence[Dict[str, Any]],
        empresa: str = EMPRESA_ALVO,
        nicho: str = NICHO,
        cidade: str = CIDADE,
        estado: str = ESTADO,
        created_at: Optional[str] = None
    ) -> Dict[str, Any]:
        return super().save_run(
            run_id=run_id,
            fontes=fontes,
            events=events,
            empresa=empresa,
            nicho=nicho,
            cidade=cidade,
            estado=estado,
            created_at=created_at or HOJE.isoformat(timespec="seconds")
        )

    def save_price_snapshots(
        self,
        run_id: str,
        snapshots: Sequence[Dict[str, Any]],
        captured_at: Optional[str] = None,
        min_change_pct: float = PRICE_HISTORY_MIN_CHANGE_PCT
    ) -> Dict[str, Any]:
        return super().save_price_snapshots(
            run_id=run_id,
            snapshots=snapshots,
            captured_at=captured_at or HOJE.isoformat(timespec="seconds"),
            min_change_pct=min_change_pct
        )

# ============================================================
# 9. MOTOR DE EVENTOS, SINAIS E SCORES (DOMAIN BINDINGS & ADAPTERS)
# ============================================================
# (Reexportados diretamente de domain.events / domain.scoring:
#  recencia_score, medir_dimensoes, score_ambiente_competitivo,
#  classificar_sinal, acao_evento, gerar_sinais_deterministicos, score_momentum)


def _primary_event_kind(f: Fonte) -> Tuple[Optional[str], List[str]]:
    return _domain_primary_event_kind(
        f,
        is_price_candidate_fn=lambda u, t, c: _price_page_type(u, t, c) in {"COMMERCIAL_CANDIDATE", "ROOT_CANDIDATE"}
    )


def criar_eventos(fontes: List[Fonte]) -> List[Dict[str, Any]]:
    return _domain_criar_eventos(
        fontes,
        hoje=HOJE,
        current_window_days=EVENT_CURRENT_WINDOW_DAYS,
        contextual_max_days=EVENT_CONTEXTUAL_MAX_DAYS,
        is_price_candidate_fn=lambda u, t, c: _price_page_type(u, t, c) in {"COMMERCIAL_CANDIDATE", "ROOT_CANDIDATE"},
        title_sim_threshold=EVENT_TITLE_SIM_THRESHOLD,
        token_sim_threshold=EVENT_TOKEN_SIM_THRESHOLD,
    )


def score_pressao_competitiva(fontes: List[Fonte], events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _domain_score_pressao_competitiva(fontes, events, empresa_alvo=EMPRESA_ALVO)


def score_vulnerabilidade_empresa(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _domain_score_vulnerabilidade_empresa(events, empresa_alvo=EMPRESA_ALVO)

# ============================================================
# 10. LLM ESTRUTURADO (LLM BINDINGS)
# ============================================================

def gerar_inteligencia_llm(
    fontes: List[Fonte],
    events: List[Dict[str, Any]],
    ambiente: Dict[str, Any],
    **kwargs: Any,
) -> Optional[Dict[str, Any]]:
    kwargs.setdefault("empresa_alvo", EMPRESA_ALVO)
    kwargs.setdefault("nicho", NICHO)
    kwargs.setdefault("cidade", CIDADE)
    kwargs.setdefault("estado", ESTADO)
    return _llm_gerar_inteligencia_llm(fontes, events, ambiente, **kwargs)

# ============================================================
# 11. MOTOR DE DECISÃO & VALIDAÇÃO FORENSE (DOMAIN BINDINGS)
# ============================================================
# Funções puras extraídas para domain.decision e reexportadas:
# inteligencia_deterministica, validar_ids_sinais, validar_pacote

# ============================================================
# 13. RENDERIZAÇÃO EXECUTIVA (REPORTS BINDINGS)
# ============================================================

def gerar_html(
    pacote: Dict[str, Any],
    fontes: List[Fonte],
    events: List[Dict[str, Any]],
    ambiente: Dict[str, Any],
    memoria: Dict[str, Any],
    **kwargs: Any,
) -> str:
    kwargs.setdefault("empresa_alvo", EMPRESA_ALVO)
    kwargs.setdefault("cidade", CIDADE)
    kwargs.setdefault("estado", ESTADO)
    kwargs.setdefault("perfil_label", PROFILE["label"])
    kwargs.setdefault("app_version", APP_VERSION)
    kwargs.setdefault("data_ref", HOJE)
    return _reports_gerar_html(pacote, fontes, events, ambiente, memoria, **kwargs)


def gerar_pdf(
    pacote: Dict[str, Any],
    fontes: List[Fonte],
    events: List[Dict[str, Any]],
    ambiente: Dict[str, Any],
    memoria: Dict[str, Any],
    **kwargs: Any,
) -> Optional[str]:
    kwargs.setdefault("empresa_alvo", EMPRESA_ALVO)
    kwargs.setdefault("cidade", CIDADE)
    kwargs.setdefault("estado", ESTADO)
    kwargs.setdefault("pasta_execucao", PASTA_EXECUCAO)
    kwargs.setdefault("run_id", RUN_ID)
    kwargs.setdefault("data_ref", HOJE)
    return _reports_gerar_pdf(pacote, fontes, events, ambiente, memoria, **kwargs)


# ============================================================
# 14. EXPORTAÇÃO (REPORTS BINDINGS)
# ============================================================

def salvar_json(nome: str, obj: Any, pasta_execucao: Optional[Path] = None) -> str:
    pasta = pasta_execucao if pasta_execucao is not None else PASTA_EXECUCAO
    return _reports_salvar_json(nome, obj, pasta_execucao=pasta)


def salvar_csv_fontes(fontes: List[Fonte], pasta_execucao: Optional[Path] = None) -> str:
    pasta = pasta_execucao if pasta_execucao is not None else PASTA_EXECUCAO
    return _reports_salvar_csv_fontes(fontes, pasta_execucao=pasta)

# ============================================================
# 15. MAIN
# ============================================================

def inicializar_tavily() -> Any:
    if not (USAR_TAVILY and CHAVE_TAVILY and TavilyClient):
        return None
    try:
        return TavilyClient(api_key=CHAVE_TAVILY)
    except Exception as e:
        logger.warning("[TAVILY] indisponível: %s", str(e)[:120])
        return None


def main() -> None:
    inicio = time.time()
    logger.info("=" * 90)
    logger.info("AGENTE SNIPER v%s", APP_VERSION)
    logger.info("Empresa=%s | Nicho=%s | Local=%s-%s", EMPRESA_ALVO, NICHO, CIDADE, ESTADO)
    logger.info("=" * 90)

    try:
        tavily_client = inicializar_tavily()
        brutas = coletar_tudo(tavily_client, session=get_http_session(), guard=_TAVILY_GUARD, io_stats=_IO_STATS)
        if not brutas:
            logger.error("[FATAL] Nenhuma busca retornou resultado.")
            return

        fontes = []
        for i, raw in enumerate(brutas, 1):
            f = transformar(raw, i)
            if f:
                fontes.append(f)
        fontes = deduplicar(fontes)
        if not fontes:
            logger.error("[FATAL] Nenhuma fonte passou por identidade/localização/data.")
            return

        fontes = enriquecer(fontes, mgr=_PLAYWRIGHT_MGR, session=get_http_session(), io_stats=_IO_STATS)
        for i, f in enumerate(fontes, 1):
            f.id = i

        events = criar_eventos(fontes)
        dimensoes = medir_dimensoes(fontes, events)
        ambiente = score_ambiente_competitivo(dimensoes)
        ambiente["dimensoes"] = dimensoes
        ambiente["momentum_mercado"] = score_momentum(events, fontes)
        ambiente["pressao_competitiva"] = score_pressao_competitiva(fontes, events)
        ambiente["vulnerabilidade_empresa"] = score_vulnerabilidade_empresa(events)

        memoria = MemoriaSniper(DB_PATH)
        comparacao_precos = comparar_precos(fontes, memoria, raw_results=brutas, tavily_client=tavily_client, nicho=NICHO)
        ambiente["comparacao_precos"] = comparacao_precos
        memoria_stats = memoria.save_run(RUN_ID, fontes, events)

        pacote = inteligencia_deterministica(fontes, events, ambiente)
        llm = gerar_inteligencia_llm(fontes, events, ambiente)
        if llm:
            base = inteligencia_deterministica(fontes, events, ambiente)
            # O LLM complementa; nunca substitui os sinais determinísticos.
            for k, v in llm.items():
                if v not in (None, "", []):
                    base[k] = v
            pacote = base
            pacote["fonte_inteligencia"] = "determinístico + LLM"
        else:
            pacote["fonte_inteligencia"] = "determinístico"

        validacao = validar_pacote(pacote, fontes)
        pacote["validacao"] = validacao
        pacote["ambiente_competitivo"] = ambiente
        pacote["comparacao_precos"] = comparacao_precos
        pacote["memoria"] = memoria_stats

        fmap = fonte_por_id(fontes)
        for s in pacote.get("sinais", []):
            s["citacao"] = ref_text([i for i in s.get("evidence_ids", []) if i in fmap])

        metricas = {
            "versao": APP_VERSION, "run_id": RUN_ID, "empresa": EMPRESA_ALVO, "nicho": NICHO,
            "local": f"{CIDADE}-{ESTADO}" if CIDADE else ESTADO,
            "fontes_brutas": len(brutas), "fontes_finais": len(fontes),
            "fontes_atuais": sum(1 for f in fontes if f.atual), "fontes_com_data": sum(1 for f in fontes if f.data_publicacao),
            "fontes_locais": sum(1 for f in fontes if f.escopo == "local"), "eventos": len(events),
            "ambiente_competitivo": ambiente, "pressao_competitiva": ambiente.get("pressao_competitiva"), "vulnerabilidade_empresa": ambiente.get("vulnerabilidade_empresa"), "comparacao_precos": comparacao_precos, "memoria": memoria_stats,
            "tempo_segundos": round(time.time() - inicio, 2),
        }

        html = gerar_html(pacote, fontes, events, ambiente, memoria_stats)
        html_path = PASTA_EXECUCAO / "dashboard.html"
        html_path.write_text(html, encoding="utf-8")
        pdf_path = gerar_pdf(pacote, fontes, events, ambiente, memoria_stats)

        json_paths = {
            "pacote": salvar_json("inteligencia.json", pacote),
            "fontes": salvar_json("fontes.json", [asdict(f) for f in fontes]),
            "eventos": salvar_json("eventos.json", events),
            "comparacao_precos": salvar_json("comparacao_precos.json", comparacao_precos),
            "metricas": salvar_json("metricas.json", metricas),
        }
        csv_path = salvar_csv_fontes(fontes)
        resumo = {"versao": APP_VERSION, "run_id": RUN_ID, "dashboard_html": str(html_path.resolve()), "pdf": pdf_path, "arquivos": json_paths, "csv": csv_path}
        salvar_json("execucao.json", resumo)

        logger.info(
            "[IO METRICS] Discovery: %.2fs (N=%d, %d tarefas) | Enrich: %.2fs (N=%d, %d tarefas) | Probes: %d (Cache hits: %d) | Sitemaps pulados: %d | HTTP 200: %d, 403: %d, 429: %d, Timeouts: %d | HTTP reqs: %d (tempo: %.2fs) | Probing total: %.2fs | Domínios únicos: %d",
            _IO_STATS["discovery_time"],
            _IO_STATS["discovery_workers"],
            _IO_STATS["discovery_tasks"],
            _IO_STATS["enrich_time"],
            _IO_STATS["enrich_workers"],
            _IO_STATS["enrich_tasks"],
            _IO_STATS["domain_probes"],
            _IO_STATS["probes_cache_hit"],
            _IO_STATS["sitemaps_skipped"],
            _IO_STATS["http_200"],
            _IO_STATS["http_403"],
            _IO_STATS["http_429"],
            _IO_STATS["http_timeouts"],
            _IO_STATS["http_requests"],
            _IO_STATS["http_time"],
            _IO_STATS["expansion_time"],
            len(_IO_STATS["unique_domains"]),
        )
        logger.info(
            "[PLAYWRIGHT METRICS] Launches: %d | Contexts: %d | Pages: %d (fechadas: %d) | Startup: %.2fs | Nav: %.2fs | Render: %.2fs | Ok: %d | Falhas: %d | Timeouts: %d",
            _PLAYWRIGHT_MGR.launch_count,
            _PLAYWRIGHT_MGR.contexts_created,
            _PLAYWRIGHT_MGR.pages_created,
            _PLAYWRIGHT_MGR.pages_closed,
            _PLAYWRIGHT_MGR.startup_time,
            _PLAYWRIGHT_MGR.navigation_time,
            _PLAYWRIGHT_MGR.render_time,
            _PLAYWRIGHT_MGR.success_count,
            _PLAYWRIGHT_MGR.fail_count,
            _PLAYWRIGHT_MGR.timeout_count,
        )
        logger.info(
            "[TAVILY METRICS] Tentativas: %d | Executadas: %d (Créditos estimados: %d) | Bloqueadas por Budget: %d | Cache hits: %d | Circuit Breaker aberto: %s | Falhas: %d",
            _TAVILY_GUARD.queries_attempted,
            _TAVILY_GUARD.queries_executed,
            _TAVILY_GUARD.estimated_credits_used,
            _TAVILY_GUARD.queries_blocked_budget,
            _TAVILY_GUARD.cache_hits,
            _TAVILY_GUARD.circuit_open,
            _TAVILY_GUARD.failures,
        )
        logger.info("=" * 90)
        logger.info("EXECUÇÃO CONCLUÍDA em %.1fs", time.time() - inicio)
        logger.info("Dashboard: %s", html_path.resolve())
        logger.info("PDF: %s", pdf_path or "não gerado")
        pressao_txt = ambiente.get("pressao_competitiva", {}).get("score")
        cp = comparacao_precos
        logger.info("Preços: %s | comparáveis=%s | alvo_mais_barato=%s | concorrente_mais_barato=%s | snapshots=%s | mudanças=%s", cp.get("status"), cp.get("comparaveis", 0), cp.get("alvo_mais_barato", 0), cp.get("concorrente_mais_barato", 0), cp.get("snapshots_observados", 0), len(cp.get("historico", {}).get("mudancas", [])))
        logger.info("Fontes: %d | Eventos: %d | Atividade empresa: %d/100 | Pressão competitiva: %s | Momentum: %d/100 | Vulnerabilidade: %d/100", len(fontes), len(events), ambiente["score"], pressao_txt if pressao_txt is not None else "N/C", ambiente["momentum_mercado"], ambiente["vulnerabilidade_empresa"]["score"])
        logger.info("=" * 90)
    finally:
        _PLAYWRIGHT_MGR.close_all()


# ============================================================
# 15.1 OFFLINE REPLAY & BENCHMARK (PIPELINE BINDINGS)
# ============================================================
# (OfflineNetworkGuard, resolver_fixture_fontes_offline, executar_replay_offline
#  reexportados de pipeline.replay)


if __name__ == "__main__":
    if "--replay-offline" in sys.argv:
        sys.exit(executar_replay_offline())
    else:
        main()
