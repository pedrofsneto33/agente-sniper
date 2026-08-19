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

import csv
import difflib
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import time
import unicodedata
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from html import unescape as html_unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus, urljoin, urlparse, urlunparse

import requests
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
    recencia_score as _domain_recencia_score,
    qualidade_fonte,
    evento_titulo_estavel,
    canonical_event_key,
    _primary_event_kind as _domain_primary_event_kind,
    eventos_sao_mesmo_fato,
    criar_eventos as _domain_criar_eventos,
)
from domain.scoring import (
    medir_dimensoes as _domain_medir_dimensoes,
    score_ambiente_competitivo as _domain_score_ambiente_competitivo,
    score_pressao_competitiva as _domain_score_pressao_competitiva,
    score_vulnerabilidade_empresa as _domain_score_vulnerabilidade_empresa,
    classificar_sinal as _domain_classificar_sinal,
    acao_evento as _domain_acao_evento,
    gerar_sinais_deterministicos as _domain_gerar_sinais_deterministicos,
    score_momentum as _domain_score_momentum,
)
from storage.sqlite import MemoriaSniper as _StorageMemoriaSniper

# ---------- dependências opcionais ----------
try:
    from groq import Groq
except Exception:
    Groq = None

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:
    genai = None
    genai_types = None

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
CIDADE = os.getenv("CIDADE", "Teresina").strip()
ESTADO = os.getenv("ESTADO", "PI").strip()
NICHO = os.getenv("NICHO", "supermercado").strip().lower()

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
PRICE_HISTORY_MIN_CHANGE_PCT = float(os.getenv("PRICE_HISTORY_MIN_CHANGE_PCT", "0.5"))
PRICE_DISCOVERY_PATH_HINTS = [
    x.strip().lower() for x in os.getenv(
        "PRICE_DISCOVERY_PATH_HINTS",
        "product|products|service|services|offer|offers|catalog|catalogue|plan|plans|price|pricing"
    ).split("|") if x.strip()
]
PRICE_BLOCKED_DOMAINS = {
    x.strip().lower() for x in os.getenv("PRICE_BLOCKED_DOMAINS", "").split("|") if x.strip()
}
PRICE_NONCOMMERCIAL_URL_HINTS = [
    x.strip().lower() for x in os.getenv(
        "PRICE_NONCOMMERCIAL_URL_HINTS", "news|noticia|noticias|article|blog|career|careers|employment|emprego"
    ).split("|") if x.strip()
]

# Sinais NEGATIVOS: página claramente não-comercial (vaga, notícia, emprego, carreira).
# Usado para impedir que o bootstrap comercial promova essas URLs a "candidata de preço"
# só porque elas mencionam a empresa-alvo/concorrente.
PRICE_NEGATIVE_PATH_HINTS = PRICE_NONCOMMERCIAL_URL_HINTS

# v11.8
EVENT_DATE_CLUSTER_DAYS = int(os.getenv("EVENT_DATE_CLUSTER_DAYS", "45"))
EVENT_TITLE_SIM_THRESHOLD = float(os.getenv("EVENT_TITLE_SIM_THRESHOLD", "0.52"))
EVENT_TOKEN_SIM_THRESHOLD = float(os.getenv("EVENT_TOKEN_SIM_THRESHOLD", "0.30"))
EVENT_CURRENT_WINDOW_DAYS = int(os.getenv("EVENT_CURRENT_WINDOW_DAYS", str(JANELA_DIAS)))
EVENT_CONTEXTUAL_MAX_DAYS = int(os.getenv("EVENT_CONTEXTUAL_MAX_DAYS", "365"))

PRICE_PAGE_NEGATIVE_TERMS = set(PRICE_NONCOMMERCIAL_URL_HINTS)
PRICE_COMMERCIAL_CONTENT_HINTS = [
    x.strip().lower() for x in os.getenv(
        "PRICE_COMMERCIAL_CONTENT_HINTS",
        "add to cart|buy now|offer|product|service|catalog|price|reserve"
    ).split("|") if x.strip()
]
PRICE_PRODUCT_SCHEMA_TYPES = {
    x.strip().lower() for x in os.getenv(
        "PRICE_COMMERCIAL_SCHEMA_TYPES", "product|service|offer|aggregateoffer"
    ).split("|") if x.strip()
}


def _is_non_commercial_url(url: str) -> bool:
    alvo = normalizar(url)
    dom = dominio(url)
    if dom in PRICE_BLOCKED_DOMAINS:
        return True
    return any(h in alvo for h in PRICE_NEGATIVE_PATH_HINTS)


def _price_page_type(url: str, title: str = "", body: str = "") -> str:
    dom = dominio(url)
    if dom in PRICE_BLOCKED_DOMAINS:
        return "BLOCKED"
    nurl = normalizar(url)
    ntitle = normalizar(title)
    nbody = normalizar(body[:5000])
    if any(h in nurl for h in PRICE_NEGATIVE_PATH_HINTS):
        return "ARTICLE_OR_EMPLOYMENT"
    if any(term in ntitle for term in PRICE_PAGE_NEGATIVE_TERMS):
        return "ARTICLE_OR_EMPLOYMENT"
    if any(term in nbody[:1800] for term in PRICE_PAGE_NEGATIVE_TERMS):
        return "ARTICLE_OR_EMPLOYMENT"
    if any(x in nurl for x in PRICE_DISCOVERY_PATH_HINTS):
        return "COMMERCIAL_CANDIDATE"
    if any(x in nbody[:1500] for x in PRICE_COMMERCIAL_CONTENT_HINTS):
        return "COMMERCIAL_CANDIDATE"
    if nurl.count("/") <= 3:
        return "ROOT_CANDIDATE"
    return "OTHER"


def _is_blocked_price_domain(url: str) -> bool:
    return _price_page_type(url) == "BLOCKED"


def is_price_candidate_url(url: str) -> bool:
    if _is_blocked_price_domain(url):
        return False
    return _commercial_signal_url(url) >= 0.45


def _commercial_signal_url(url: str) -> float:
    if not url:
        return -1.0
    dom = dominio(url)
    if dom in PRICE_BLOCKED_DOMAINS:
        return -1.0
    path = normalizar(urlparse(url).path)
    full = normalizar(url)
    negative = any(term in full for term in PRICE_NONCOMMERCIAL_URL_HINTS)
    score = 0.0
    if any(h in path for h in PRICE_DISCOVERY_PATH_HINTS):
        score += 0.20
    if path in {"","/","/home","/index.html","/index.php"}:
        score += 0.05
    if negative:
        score -= 0.15
    return max(-1.0, min(1.0, score))


def carregar_price_sources() -> List[Dict[str, Any]]:
    if PRECO_SOURCES_JSON:
        try:
            obj = json.loads(PRECO_SOURCES_JSON)
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict) and x.get("name")]
        except Exception:
            pass
    return [{"name": EMPRESA_ALVO, "role": "target", "url": u} for u in PRECO_ALVO_URLS]

PRICE_SOURCES = carregar_price_sources()
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
# 2. PERFIS DE NICHO
# ============================================================

NICHE_PROFILES: Dict[str, Dict[str, Any]] = {
    "supermercado": {
        "label": "Varejo alimentar",
        "queries": [
            "preço oferta promoção cesta concorrente",
            "reclamação atendimento fila produto entrega",
            "inauguração loja expansão app delivery fidelidade",
            "Procon fiscalização vigilância sanitária",
            "emprego contratação nova unidade",
        ],
        "signals": ["preço", "oferta", "promoção", "fila", "produto", "entrega", "loja", "app", "delivery", "inauguração"],
    },
    "restaurante": {
        "label": "Alimentação e hospitalidade",
        "queries": [
            "preço cardápio promoção delivery concorrente",
            "avaliação reclamação atendimento qualidade",
            "nova unidade expansão franquia",
            "iFood delivery aplicativo marketing",
            "fiscalização vigilância sanitária",
        ],
        "signals": ["cardápio", "preço", "delivery", "avaliação", "atendimento", "franquia", "unidade"],
    },
    "clinica": {
        "label": "Saúde e serviços clínicos",
        "queries": [
            "serviços especialidades preço convênio",
            "avaliação reclamação atendimento",
            "nova unidade médicos contratação",
            "marketing tecnologia agendamento aplicativo",
            "licença fiscalização regulação",
        ],
        "signals": ["especialidade", "convênio", "consulta", "avaliação", "atendimento", "agendamento", "unidade"],
    },
    "hotel": {
        "label": "Hotelaria",
        "queries": [
            "diária preço promoção concorrente",
            "avaliação reclamação atendimento",
            "ocupação expansão nova unidade",
            "booking hoteis.com turismo eventos",
            "serviços experiência hóspede",
        ],
        "signals": ["diária", "hotel", "reserva", "ocupação", "avaliação", "hóspede", "serviço"],
    },
    "farmacia": {
        "label": "Varejo farmacêutico",
        "queries": [
            "preço promoção medicamento concorrente",
            "avaliação atendimento entrega",
            "nova loja expansão",
            "app delivery fidelidade",
            "Anvisa Procon fiscalização",
        ],
        "signals": ["preço", "promoção", "medicamento", "delivery", "farmácia", "loja", "Anvisa"],
    },
    "imobiliaria": {
        "label": "Mercado imobiliário",
        "queries": [
            "lançamento preço imóvel concorrente",
            "avaliação atendimento corretores",
            "novos empreendimentos expansão",
            "marketing leads digital",
            "mercado vendas aluguel",
        ],
        "signals": ["imóvel", "lançamento", "preço", "aluguel", "vendas", "leads", "empreendimento"],
    },
    "tecnologia": {
        "label": "Tecnologia e SaaS",
        "queries": [
            "produto lançamento preço concorrente",
            "avaliação cliente churn reclamação",
            "parceria investimento aquisição",
            "feature roadmap tecnologia",
            "contratação engenharia vendas",
        ],
        "signals": ["produto", "SaaS", "preço", "feature", "API", "parceria", "investimento"],
    },
    "educacao": {
        "label": "Educação",
        "queries": [
            "curso preço matrícula promoção concorrente",
            "avaliação aluno atendimento",
            "nova unidade expansão",
            "plataforma aplicativo tecnologia",
            "vagas contratação professores",
        ],
        "signals": ["curso", "mensalidade", "matrícula", "aluno", "professor", "plataforma", "unidade"],
    },
    "varejo": {
        "label": "Varejo geral",
        "queries": [
            "preço promoção produto concorrente",
            "avaliação atendimento entrega",
            "nova loja expansão",
            "e-commerce aplicativo fidelidade",
            "campanha marketing lançamento",
        ],
        "signals": ["preço", "promoção", "produto", "loja", "e-commerce", "app", "campanha"],
    },
    "servicos": {
        "label": "Serviços",
        "queries": [
            "preço serviço concorrente",
            "avaliação reclamação atendimento",
            "expansão nova unidade contratação",
            "digital aplicativo agendamento",
            "marketing parceria campanha",
        ],
        "signals": ["preço", "serviço", "avaliação", "atendimento", "agendamento", "parceria"],
    },
    "generico": {
        "label": "Empresa genérica",
        "queries": [
            "preço produto serviço concorrente",
            "avaliação reclamação atendimento",
            "expansão nova unidade contratação",
            "produto tecnologia marketing",
            "regulação fiscalização parceria",
        ],
        "signals": ["preço", "produto", "serviço", "avaliação", "expansão", "tecnologia", "marketing"],
    },
}

PROFILE = NICHE_PROFILES.get(NICHO, NICHE_PROFILES["generico"])

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


def identidade_conflitante(texto: str, empresa_alvo: str = EMPRESA_ALVO) -> bool:
    return _domain_identidade_conflitante(texto, empresa_alvo)


def cidade_ok(texto: str, cidade: str = CIDADE) -> bool:
    return _domain_cidade_ok(texto, cidade)


def estado_ok(texto: str, estado: str = ESTADO) -> bool:
    return _domain_estado_ok(texto, estado)


def json_seguro(texto: str) -> Optional[Dict[str, Any]]:
    if not texto:
        return None
    s = texto.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except Exception:
        return None


def source_domain_root(url: str) -> str:
    return dominio(url)
    return dominio(url)

def _fetch_html_http(url: str) -> Tuple[str, str]:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        ctype = (r.headers.get("content-type") or "").lower()
        if r.ok and "html" in ctype and len(r.text) > 500:
            return r.text, r.url
    except Exception as e:
        logger.debug("[PRICE DISCOVERY HTTP] %s", str(e)[:120])
    return "", url


def _extract_commercial_links(base_url: str, html: str, limit: int = 20) -> List[str]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    base = urlparse(base_url)
    ranked = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        try:
            u = urljoin(base_url, href)
            pu = urlparse(u)
        except Exception:
            continue
        if pu.scheme not in {"http", "https"}:
            continue
        if _is_blocked_price_domain(u) or _is_non_commercial_url(u):
            continue
        txt = normalizar(a.get_text(" ", strip=True))
        same_domain = pu.netloc == base.netloc
        signal = _commercial_signal_url(u)
        anchor_signal = any(k in txt for k in [
            "comprar", "loja", "loja online", "shop", "supermarket", "supershop",
            "produto", "produtos", "oferta", "ofertas", "catalogo", "catálogo",
            "preco", "preço", "servicos", "serviços", "cardapio", "menu", "reservar"
        ])
        if anchor_signal:
            signal += 0.35
        # Externo só entra com forte sinal comercial; interno pode entrar com sinal moderado.
        if (not same_domain) and signal < 0.70:
            continue
        if signal <= 0.0:
            continue
        un = url_normalizada(u)
        if un in seen:
            continue
        seen.add(un)
        ranked.append((signal, un))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [u for _, u in ranked[:limit]]


def _expand_commercial_domain(url: str, name: str, role: str, location_note: str = "") -> List[Dict[str, Any]]:
    if _is_blocked_price_domain(url):
        return []
    dom = source_domain_root(url)
    if not dom:
        return []
    candidates = [url]
    root = f"https://{dom}"
    if root not in candidates:
        candidates.append(root)
    sitemap_urls = [f"https://{dom}/sitemap.xml", f"https://{dom}/sitemap_index.xml"]
    discovered = []
    for seed in candidates + sitemap_urls:
        html, final = _fetch_html_http(seed)
        if html:
            if seed.endswith("sitemap.xml") or seed.endswith("sitemap_index.xml"):
                for m in re.finditer(r"<loc>(.*?)</loc>", html, flags=re.I | re.S):
                    u = html_unescape(m.group(1).strip())
                    if urlparse(u).netloc == dom or urlparse(u).netloc.endswith("." + dom):
                        if is_price_candidate_url(u):
                            discovered.append(u)
            else:
                discovered.append(final)
                discovered.extend(_extract_commercial_links(final, html, PRICE_CRAWL_LINK_LIMIT))
    uniq=[]; seen=set()
    for u in discovered:
        if u in seen or _is_blocked_price_domain(u): continue
        seen.add(u)
        uniq.append({"name":name,"role":role,"url":u,"domain":dom,"location_note":location_note,"discovered":True})
    uniq.sort(key=lambda x: _commercial_signal_url(x["url"]), reverse=True)
    return uniq[:PRICE_DISCOVERY_LIMIT_PER_ENTITY]


def _discover_official_commercial_urls(fontes: List[Fonte]) -> List[Dict[str, Any]]:
    """Usa URLs já coletadas para inferir domínios comerciais candidatos, mas nunca promove
    redes sociais/diretórios/notícias como catálogo. A expansão acontece depois no domínio.
    """
    candidatos: List[Dict[str, Any]] = []
    seen = set()
    for f in fontes:
        if not f.entidade or f.entidade == "mercado":
            continue
        dom = source_domain_root(f.url)
        if not dom or _is_blocked_price_domain(f.url):
            continue
        # Domínios de notícia/emprego podem aparecer, mas não são aceitos como fonte final;
        # só entram se a própria página possuir sinal comercial forte.
        sig = _commercial_signal_url(f.url)
        if sig <= 0:
            continue
        key=(normalizar(f.entidade),dom)
        if key in seen:
            continue
        seen.add(key)
        role="target" if normalizar(f.entidade)==normalizar(EMPRESA_ALVO) else "competitor"
        candidatos.extend(_expand_commercial_domain(f.url, f.entidade, role,
            "localidade confirmada" if f.cidade_confirmada else "localidade não confirmada"))
    return candidatos


def descobrir_fontes_preco(fontes: List[Fonte], raw_results: Optional[List[Dict[str, Any]]] = None, tavily_client: Any = None) -> List[Dict[str, Any]]:
    if not PRICE_SITE_DISCOVERY:
        return []
    grupos: Dict[str, List[Fonte]] = {}
    auto_candidates: List[Dict[str, Any]] = []

    # 0) Descoberta direta em resultados brutos já coletados. Isso evita perder o domínio oficial
    # durante a normalização/filtro factual.
    if raw_results:
        seen_raw=set()
        for r in raw_results:
            alvo=str(r.get("alvo") or "").strip()
            if not alvo or alvo == "mercado":
                continue
            url=str(r.get("url") or "").strip()
            dom=source_domain_root(url)
            if not dom or _is_blocked_price_domain(url):
                continue
            key=(normalizar(alvo),dom)
            if key in seen_raw:
                continue
            # Somente páginas com sinais comerciais ou domínios raiz de propriedade da entidade.
            title=normalizar(str(r.get("titulo") or ""))
            body=normalizar(str(r.get("conteudo") or ""))
            sig=_commercial_signal_url(url)
            official_hint=any(k in title or k in body for k in [
                "comprar online","loja online","loja virtual","catalogo","produtos","ofertas","precos","supershop","ecommerce"
            ])
            if sig <= 0 and not official_hint:
                continue
            role="target" if normalizar(alvo)==normalizar(EMPRESA_ALVO) else "competitor"
            auto_candidates.extend(_expand_commercial_domain(url, alvo, role, "descoberta comercial"))
            seen_raw.add(key)

    # 0b) Busca comercial adicional usando Tavily, se disponível. Isso é propositalmente
    # limitado para não explodir créditos.
    if PRICE_AUTO_SEARCH_COMMERCIAL and tavily_client:
        entities=[EMPRESA_ALVO]+[c for c in CONCORRENTES if c]
        for ent in entities[:PRICE_COMMERCIAL_QUERY_LIMIT+1]:
            queries=[
                f'"{ent}" {CIDADE} site oficial comprar online',
                f'"{ent}" {CIDADE} produtos ofertas preços',
            ]
            for q in queries[:PRICE_COMMERCIAL_QUERY_LIMIT]:
                try:
                    rr=tavily_client.search(query=q,max_results=5,search_depth="basic",include_answer=False)
                    for x in rr.get("results",[]):
                        url=str(x.get("url") or "").strip(); dom=source_domain_root(url)
                        if not dom or _is_blocked_price_domain(url):
                            continue
                        role="target" if normalizar(ent)==normalizar(EMPRESA_ALVO) else "competitor"
                        auto_candidates.extend(_expand_commercial_domain(url,ent,role,"busca comercial automática"))
                except Exception as e:
                    logger.warning("[PREÇOS AUTO SEARCH] %s", str(e)[:120])
    # 1) fontes com URLs claramente comerciais
    for f in fontes:
        if f.entidade and f.entidade not in {"mercado", ""} and is_price_candidate_url(f.url):
            grupos.setdefault(f.entidade, []).append(f)
    # 2) bootstrap oficial/comercial: qualquer domínio corporativo confiável da entidade.
    for f in fontes:
        if not f.entidade or f.entidade == "mercado" or _is_blocked_price_domain(f.url):
            continue
        dom = dominio(f.url)
        if not dom:
            continue
        # Não promover uma fonte de vaga/notícia/emprego para catálogo.
        if _is_non_commercial_url(f.url) or _is_non_commercial_url(f.titulo):
            continue
        grupos.setdefault(f.entidade, [])
        if len(grupos[f.entidade]) < PRICE_DISCOVERY_LIMIT_PER_ENTITY:
            grupos[f.entidade].append(f)
    out=[]
    out.extend(auto_candidates)
    out.extend(_discover_official_commercial_urls(fontes))
    for entidade, fs in grupos.items():
        role="target" if normalizar(entidade)==normalizar(EMPRESA_ALVO) else "competitor"
        ordered=sorted(fs, key=lambda x:(1 if is_price_candidate_url(x.url) else 0, x.direta, x.cidade_confirmada, x.atual, x.score), reverse=True)
        seen_domains=set(); count=0
        for f in ordered:
            dom=source_domain_root(f.url)
            if not dom or dom in seen_domains or _is_blocked_price_domain(f.url):
                continue
            # Evitar jornal/diretório como fonte comercial primária.
            if PRICE_REQUIRE_COMMERCIAL_SIGNAL and _commercial_signal_url(f.url) <= 0:
                # ainda assim pode ser bootstrap de domínio; expandiremos a raiz e só manteremos links comerciais.
                expanded=_expand_commercial_domain(f.url, entidade, role, "localidade confirmada" if f.cidade_confirmada else "localidade não confirmada")
                for src in expanded:
                    if src["domain"] not in seen_domains:
                        out.append(src); seen_domains.add(src["domain"]); count += 1
                    if count >= PRICE_DISCOVERY_LIMIT_PER_ENTITY: break
                continue
            out.append({"name":entidade,"role":role,"url":f.url,"domain":dom,"location_note":"localidade confirmada" if f.cidade_confirmada else "localidade não confirmada","discovered":True})
            seen_domains.add(dom); count += 1
            if count >= PRICE_DISCOVERY_LIMIT_PER_ENTITY: break
    # Sempre expandir os dois primeiros domínios por entidade para encontrar /shop, /catalog, /colecoes etc.
    expanded_out=[]
    for src in out:
        expanded_out.append(src)
    entities={src["name"] for src in out}
    for entity in entities:
        base=[src for src in out if src["name"]==entity][:PRICE_MAX_DOMAINS_PER_ENTITY]
        for src in base:
            expanded_out.extend(_expand_commercial_domain(src["url"], entity, src["role"], src.get("location_note","")))
    uniq=[]; seen=set()
    for src in expanded_out:
        k=(normalizar(src.get("name","")), src.get("domain") or source_domain_root(src.get("url","")), src.get("role",""), src.get("url",""))
        if not src.get("url") or k in seen: continue
        seen.add(k); uniq.append(src)
    return uniq


def mesclar_price_sources(fontes: List[Fonte], raw_results: Optional[List[Dict[str, Any]]] = None, tavily_client: Any = None) -> List[Dict[str, Any]]:
    merged=[]; seen=set()
    for src in list(PRICE_SOURCES)+descobrir_fontes_preco(fontes, raw_results=raw_results, tavily_client=tavily_client):
        name=str(src.get("name") or "").strip(); url=str(src.get("url") or "").strip()
        if not name or not url:
            continue
        key=(normalizar(name), source_domain_root(url), str(src.get("role","competitor")))
        if key in seen:
            continue
        seen.add(key); merged.append(src)
    return merged

# ============================================================
# 5. BUSCAS
# ============================================================

def gerar_consultas() -> Dict[str, List[Tuple[str, str]]]:
    emp = f'"{EMPRESA_ALVO}"'
    local = f'"{CIDADE}"' if CIDADE else ""
    empresa = []
    for q in PROFILE["queries"]:
        empresa.append((f"{emp} {local} {q} {HOJE.year}".strip(), EMPRESA_ALVO))
    empresa.extend([
        (f"{emp} {local} notícias {HOJE.year}".strip(), EMPRESA_ALVO),
        (f"{emp} {local} expansão concorrentes mercado {HOJE.year}".strip(), EMPRESA_ALVO),
    ])
    mercado = [
        (f"{NICHO} {local} mercado tendências preço comportamento {HOJE.year}".strip(), "mercado"),
        (f"{NICHO} Brasil tendências {HOJE.year}".strip(), "mercado"),
    ]
    concorrencia = []
    comercial = [
        (f'{emp} {local} comprar online loja virtual catalogo produtos preços ofertas {HOJE.year}'.strip(), EMPRESA_ALVO),
        (f'{emp} {local} site oficial supershop loja compras {HOJE.year}'.strip(), EMPRESA_ALVO),
    ]
    for nome in CONCORRENTES:
        concorrencia.extend([
            (f'"{nome}" {local} preço promoção expansão notícias {HOJE.year}'.strip(), nome),
            (f'"{nome}" {local} reclamação atendimento avaliação {HOJE.year}'.strip(), nome),
            (f'"{nome}" {local} aplicativo delivery marketing {HOJE.year}'.strip(), nome),
        ])
        comercial.extend([
            (f'"{nome}" {local} comprar online loja virtual catalogo produtos preços ofertas {HOJE.year}'.strip(), nome),
            (f'"{nome}" {local} site oficial loja compras catálogo {HOJE.year}'.strip(), nome),
        ])
    return {"empresa": empresa, "concorrencia": concorrencia, "comercial": comercial, "mercado": mercado}


def buscar_tavily(client: Any, query: str, categoria: str) -> List[Dict[str, Any]]:
    if not client:
        return []
    try:
        r = client.search(query=query, max_results=5, search_depth="basic", include_answer=False)
        return [
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
    except Exception as e:
        logger.warning("[TAVILY] %s", str(e)[:160])
        return []


def buscar_ddg(query: str, categoria: str) -> List[Dict[str, Any]]:
    if not DDGS or not USAR_DDG:
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


def buscar_news_rss(query: str, categoria: str) -> List[Dict[str, Any]]:
    if not USAR_NEWS_RSS:
        return []
    try:
        url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
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


def coletar_tudo(tavily_client: Any) -> List[Dict[str, Any]]:
    consultas = gerar_consultas()
    todas: List[Dict[str, Any]] = []
    max_por_grupo = int(os.getenv("MAX_CONSULTAS_POR_GRUPO", "5"))
    for grupo, itens in consultas.items():
        itens_exec = itens[:max_por_grupo]
        logger.info("[COLETA] %s | %d consultas", grupo, len(itens_exec))
        for q, alvo in itens_exec:
            resultados = []
            resultados.extend(buscar_tavily(tavily_client, q, grupo) if USAR_TAVILY else [])
            resultados.extend(buscar_ddg(q, grupo))
            resultados.extend(buscar_news_rss(q, grupo))
            for r in resultados:
                r["alvo"] = alvo
            todas.extend(resultados)
            time.sleep(float(os.getenv("PAUSA_BUSCA", "0.35")))
    logger.info("[COLETA] %d resultados brutos", len(todas))
    return todas

# ============================================================
# 6. VALIDAÇÃO / NORMALIZAÇÃO DAS FONTES
# ============================================================

DOMINIOS_PRIORITARIOS = {
    "gov.br": 1.00,
    "reclameaqui.com.br": 0.95,
    "procon": 0.95,
    "g1.globo.com": 0.92,
    "cidadeverde.com": 0.92,
    "portalodia.com": 0.90,
    "meionews.com": 0.88,
    "mppi.mp.br": 0.98,
    "gruporcarvalho.com.br": 0.85,
}

CIDADES_EXTERIORES = {
    "jundiai", "cubatao", "redmond", "washington", "new york", "california", "florida",
    "texas", "miami", "los angeles", "london", "madrid", "lisboa", "paris",
}


def score_fonte(f: Fonte) -> float:
    s = 0
    if f.alias_empresa:
        s += 34
    if f.cidade_confirmada:
        s += 18
    elif f.estado_confirmado:
        s += 8
    if f.atual:
        s += 18
    elif not f.data_publicacao:
        s -= 8
    if f.direta:
        s += 7
    if len(f.conteudo) >= 1000:
        s += 5
    if f.escopo == "local":
        s += 6
    elif f.escopo == "corporativo":
        s += 4
    d = f.dominio
    for dom, peso in DOMINIOS_PRIORITARIOS.items():
        if d == dom or dom in d:
            s += 8 * peso
            break
    sinais = f.sinais
    s += min(10, 2 * len(sinais))
    return s


def classificar_escopo(texto: str, corporativo: bool) -> Tuple[str, bool, bool]:
    c, e = cidade_ok(texto), estado_ok(texto)
    n = normalizar(texto)
    exterior = any(termo(n, x) for x in CIDADES_EXTERIORES)
    if exterior and not (c or e):
        return "global", c, e
    if c:
        return "local", c, e
    if e:
        return "nacional", c, e
    if corporativo:
        return "corporativo", c, e
    return "incerto", c, e


def sinais_deterministicos(texto: str) -> List[str]:
    n = normalizar(texto)
    regras = {
        "preço": ["preco", "promocao", "oferta", "desconto", "r$"],
        "reputação": ["reclamacao", "reclame", "avaliacao", "nota", "queixa"],
        "atendimento": ["atendimento", "fila", "demora", "suporte", "servico"],
        "expansão": ["inaugur", "nova unidade", "nova loja", "expansao", "filial"],
        "digital": ["app", "aplicativo", "delivery", "e-commerce", "ecommerce", "plataforma"],
        "marketing": ["campanha", "publicidade", "patrocin", "evento", "marketing"],
        "pessoas": ["vaga", "contratacao", "emprego", "recrut", "funcionario"],
        "regulação": ["procon", "multa", "fiscalizacao", "sanitaria", "anvisa", "processo"],
        "produto": ["produto", "lancamento", "catalogo", "servico", "cardapio"],
        "parceria": ["parceria", "acordo", "joint venture", "fornecedor"],
    }
    out = []
    for tag, palavras in regras.items():
        if any(p in n for p in palavras):
            out.append(tag)
    return out


def transformar(raw: Dict[str, Any], idx: int) -> Optional[Fonte]:
    titulo = str(raw.get("titulo", "")).strip()
    url = url_normalizada(str(raw.get("url", "")).strip())
    snippet = str(raw.get("conteudo", "")).strip()
    if not url:
        return None
    texto = f"{titulo}\n{url}\n{snippet}"
    alvo = str(raw.get("alvo") or "").strip()
    if alvo != "mercado" and identidade_conflitante(texto):
        return None
    a = alias_empresa(texto)
    if not a and alvo and alvo != "mercado" and not termo(texto, alvo):
        return None
    if not a and alvo and alvo != "mercado":
        a = alvo
    if not a and alvo != "mercado":
        return None
    corporativo = any(k in dominio(url) for k in [normalizar(x).replace(" ", "") for x in [EMPRESA_ALVO, alvo, "grupo", "corporate"] if x])
    escopo, c, e = classificar_escopo(texto, corporativo)
    if alvo == "mercado":
        escopo = "mercado" if not c else "local"
    elif alvo and alvo != EMPRESA_ALVO and alvo != "mercado" and termo(texto, alvo):
        # Evidência de concorrente: pode ser nacional/corporativa, mas não deve ser confundida com a empresa-alvo.
        escopo = "concorrente" if not c else "local"
    else:
        # Empresa-alvo: rejeitar fontes geograficamente incompatíveis.
        if CIDADE and escopo == "global":
            return None
        if CIDADE and escopo == "incerto" and not corporativo:
            return None
    data, tipo, d = data_publicacao(raw)
    if d and d.year < ANO_MINIMO_HISTORICO:
        return None
    sinais = sinais_deterministicos(texto)
    f = Fonte(
        id=idx,
        titulo=titulo or url,
        url=url,
        origem=str(raw.get("origem", "web")),
        categoria=str(raw.get("categoria", "geral")),
        entidade=alvo or a or "mercado",
        conteudo=snippet,
        resumo_busca=snippet,
        data_publicacao=data,
        data_tipo=tipo,
        atual=bool(d and d.year >= ANO_MINIMO_ATUAL),
        direta=False,
        alias_empresa=a,
        cidade_confirmada=c,
        estado_confirmado=e,
        escopo=escopo,
        fingerprint=sha1(normalizar(titulo + " " + snippet[:2400] + " " + url)),
        dominio=dominio(url),
        sinais=sinais,
    )
    f.confianca = min(1.0, 0.45 + (0.2 if a else 0) + (0.15 if c else 0) + (0.12 if e else 0) + (0.08 if d else 0))
    f.score = score_fonte(f)
    return f


def deduplicar(fontes: List[Fonte]) -> List[Fonte]:
    vistos_url, vistos_fp = set(), set()
    out = []
    for f in sorted(fontes, key=lambda x: x.score, reverse=True):
        if f.url in vistos_url or f.fingerprint in vistos_fp:
            continue
        vistos_url.add(f.url)
        vistos_fp.add(f.fingerprint)
        out.append(f)
    for i, f in enumerate(out, 1):
        f.id = i
    return out

# ============================================================
# 7. EXTRAÇÃO DIRETA
# ============================================================

def extrair_html(url: str) -> Dict[str, Any]:
    r = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"},
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    r.raise_for_status()
    return {"html": r.text, "final_url": r.url, "content_type": r.headers.get("content-type", "")}


def extrair_playwright(url: str) -> Optional[Dict[str, Any]]:
    if not PLAYWRIGHT_ATIVO:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT, locale="pt-BR")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            texto = page.locator("body").inner_text(timeout=12000)
            out = {"conteudo": texto, "titulo": page.title(), "final_url": page.url, "data_publicacao": ""}
            browser.close()
            return out
    except Exception as e:
        logger.debug("[PW] %s", str(e)[:150])
        return None


def extrair_pagina(url: str) -> Dict[str, Any]:
    try:
        raw = extrair_html(url)
        ctype = (raw.get("content_type") or "").lower()
        if "html" not in ctype and "xhtml" not in ctype:
            raise RuntimeError("não HTML")
        soup = BeautifulSoup(raw["html"], "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
            tag.decompose()
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
        texto = soup.get_text("\n", strip=True)
        texto = re.sub(r"\n{3,}", "\n\n", texto)
        if len(texto) < 250 and PLAYWRIGHT_ATIVO:
            raise RuntimeError("página quase vazia")
        return {"titulo": title, "conteudo": texto, "data_publicacao": pub, "final_url": raw["final_url"], "direta": True}
    except Exception:
        pw = extrair_playwright(url)
        if pw:
            return {**pw, "direta": True}
        return {"titulo": "", "conteudo": "", "data_publicacao": "", "final_url": url, "direta": False}


def enriquecer(fontes: List[Fonte]) -> List[Fonte]:
    alvo = sorted(fontes, key=lambda x: x.score, reverse=True)[:MAX_ENRIQUECIMENTO]
    for i, f in enumerate(alvo, 1):
        logger.info("[EXTRAÇÃO %02d/%02d] %s", i, len(alvo), f.url)
        dados = extrair_pagina(f.url)
        if not dados.get("conteudo"):
            continue
        old_snippet = f.resumo_busca
        f.titulo = truncar(dados.get("titulo") or f.titulo, 320)
        f.conteudo = truncar(dados.get("conteudo"), 18000)
        f.resumo_busca = old_snippet
        f.direta = bool(dados.get("direta"))
        f.data_publicacao = str(dados.get("data_publicacao") or f.data_publicacao)
        if f.data_publicacao:
            d = parse_data(f.data_publicacao)
            if d:
                f.atual = d.year >= ANO_MINIMO_ATUAL
                f.data_tipo = "publicada"
        f.url = url_normalizada(dados.get("final_url") or f.url)
        combined = f.texto()
        a = alias_empresa(combined)
        if a:
            f.alias_empresa = a
        f.cidade_confirmada = cidade_ok(combined)
        f.estado_confirmado = estado_ok(combined)
        if f.cidade_confirmada:
            f.escopo = "local"
        elif f.estado_confirmado:
            f.escopo = "nacional"
        f.sinais = sinais_deterministicos(combined)
        f.score = score_fonte(f)
        time.sleep(0.06)

    for i, f in enumerate(sorted(fontes, key=lambda x: x.score, reverse=True), 1):
        f.id = i
    return sorted(fontes, key=lambda x: x.score, reverse=True)[:MAX_FONTES_FINAIS]

# ============================================================
# 8. MONITORAMENTO DE PREÇOS E PROMOÇÕES
# ============================================================

MONEY_RE = re.compile(r"R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?|[0-9]+(?:\.[0-9]{2}))", re.I)


def _walk_json(obj: Any, limit: int = 10000) -> Iterable[Dict[str, Any]]:
    stack = [obj]
    seen = 0
    while stack and seen < limit:
        cur = stack.pop()
        seen += 1
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def _extract_price_from_obj(obj: Dict[str, Any]) -> Optional[float]:
    keys = ["price", "lowPrice", "salePrice", "sellingPrice", "bestPrice", "currentPrice", "value"]
    for key in keys:
        if key in obj:
            p = parse_money(obj.get(key))
            if p is not None and p > 0:
                return p
    offers = obj.get("offers")
    if isinstance(offers, dict):
        for key in ["price", "lowPrice", "priceSpecification"]:
            val = offers.get(key)
            if isinstance(val, dict):
                p = _extract_price_from_obj(val)
                if p is not None:
                    return p
            else:
                p = parse_money(val)
                if p is not None and p > 0:
                    return p
    if isinstance(offers, list):
        for item in offers:
            if isinstance(item, dict):
                p = _extract_price_from_obj(item)
                if p is not None:
                    return p
    return None


def _schema_types(obj: Dict[str, Any]) -> set:
    vals=obj.get("@type") or obj.get("type")
    if isinstance(vals,str): return {normalizar(vals)}
    if isinstance(vals,list): return {normalizar(v) for v in vals if isinstance(v,str)}
    return set()


def _plausible_price(name: str, price: Optional[float], context: str = "") -> bool:
    if price is None or price<=0 or price>1_000_000:
        return False
    n=normalizar(name+" "+context)
    bad=["pib","receita","lucro","investimento","caixa","milhoes","milhões","bilhoes","bilhões","cotacao","cotação","dividend","acoes","ações","salario","salário","vaga","emprego","patrimonio","patrimônio"]
    return not any(x in n for x in bad)


def _price_item_confidence(obj: Dict[str, Any], page_type: str, name: str, price: Optional[float]) -> float:
    if not name or price is None or price<=0: return 0.0
    types=_schema_types(obj)
    score=0.40
    if types & PRICE_PRODUCT_SCHEMA_TYPES: score+=0.35
    if any(obj.get(k) for k in ["sku","productId","gtin","gtin13","mpn"]): score+=0.10
    if page_type in {"COMMERCIAL_CANDIDATE","ROOT_CANDIDATE"}: score+=0.10
    if obj.get("brand"): score+=0.05
    return min(score,1.0)


def _extract_product_objects(html: str, source: str, role: str, page_url: str, location_note: str = "") -> List[PriceItem]:
    soup=BeautifulSoup(html or "","html.parser")
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    body=soup.get_text(" ",strip=True)[:7000]
    page_type=_price_page_type(page_url,title,body)
    if page_type in {"BLOCKED","ARTICLE_OR_EMPLOYMENT"}:
        return []
    found={}
    for s in soup.find_all("script"):
        raw=s.string or s.get_text(" ",strip=True)
        if not raw or len(raw)<20: continue
        objs=[]
        if s.get("type")=="application/ld+json":
            try: objs=list(_walk_json(json.loads(raw),12000))
            except Exception: objs=[]
        elif page_type=="COMMERCIAL_CANDIDATE":
            for m in re.finditer(r"\{.{0,5000}?(?:price|salePrice|sellingPrice).{0,5000}?\}",raw,flags=re.I|re.S):
                try: objs.append(json.loads(m.group(0)))
                except Exception: pass
        for obj in objs:
            types=_schema_types(obj)
            if types and not (types & PRICE_PRODUCT_SCHEMA_TYPES) and not ("offers" in obj and obj.get("name")):
                continue
            name=str(obj.get("name") or obj.get("productName") or obj.get("title") or "").strip()
            price=_extract_price_from_obj(obj)
            if not name or not _plausible_price(name,price,str(obj.get("description") or "")): continue
            conf=_price_item_confidence(obj,page_type,name,price)
            if conf<0.70: continue
            brand=obj.get("brand")
            if isinstance(brand,dict): brand=brand.get("name","")
            old_price=None
            for k2 in ["oldPrice","listPrice","compareAtPrice","originalPrice"]:
                if k2 in obj:
                    old_price=parse_money(obj.get(k2))
                    if old_price: break
            unit=str(obj.get("unit") or obj.get("size") or obj.get("quantity") or "").strip()
            sku=str(obj.get("sku") or obj.get("productId") or obj.get("gtin") or obj.get("gtin13") or obj.get("mpn") or "").strip()
            key=normalizar(f"{name} {brand or ''} {unit} {sku}")
            item=PriceItem(source,role,name,page_url,price,old_price,bool(old_price and old_price>price),str(brand or ""),unit,sku,location_note=location_note,evidence_url=page_url)
            item.page_type=page_type
            item.price_confidence=conf
            found.setdefault(key,item)
    if page_type in {"COMMERCIAL_CANDIDATE","ROOT_CANDIDATE"}:
        for node in soup.find_all(string=MONEY_RE):
            parent=node.parent
            if not parent: continue
            container=parent
            for _ in range(2):
                if getattr(container,"parent",None): container=container.parent
            context=container.get_text(" ",strip=True)
            prices=[parse_money(m.group(1)) for m in MONEY_RE.finditer(context)]
            if not prices: continue
            price=prices[-1]
            links=[a.get_text(" ",strip=True) for a in container.find_all("a") if a.get_text(" ",strip=True)]
            candidate=" ".join(links[:3]).strip()
            if len(candidate)<5: candidate=re.sub(r"R\$\s*[0-9.,]+"," ",context)
            candidate=re.sub(r"\s+"," ",candidate).strip()
            if not (5<=len(candidate)<=180) or not _plausible_price(candidate,price,context): continue
            if not any(k in normalizar(context) for k in ["comprar","carrinho","produto","oferta","promocao","promoção","preco","preço","servico","serviço","cardapio","reservar"]): continue
            key=normalizar(candidate)
            item=PriceItem(source,role,candidate,page_url,price,None,False,"","", "",location_note=location_note,evidence_url=page_url)
            item.page_type=page_type
            item.price_confidence=0.78
            found.setdefault(key,item)
    return list(found.values())


def _price_page_html(url: str, use_playwright: bool = True) -> Tuple[str, str]:
    global _PRICE_FETCH_COUNT
    key = url_normalizada(url)
    cached = _PRICE_HTTP_CACHE.get(key)
    if cached and time.time() - cached[2] < 21600:
        return cached[0], cached[1]
    if _PRICE_FETCH_COUNT >= PRICE_MAX_HTTP_FETCHES:
        logger.info("[PREÇO BUDGET] limite de fetch atingido: %d", PRICE_MAX_HTTP_FETCHES)
        return "", url
    _PRICE_FETCH_COUNT += 1
    try:
        r = requests.get(key, headers={"User-Agent": USER_AGENT}, timeout=min(REQUEST_TIMEOUT, 12), allow_redirects=True)
        if r.ok and "html" in (r.headers.get("content-type") or "").lower() and len(r.text) > 1000:
            _PRICE_HTTP_CACHE[key]=(r.text, r.url, time.time())
            return r.text, r.url
    except Exception as e:
        logger.debug("[PREÇO HTTP] %s", str(e)[:120])
    # Playwright somente em URL fortemente candidata a comercial/dinâmica.
    if not (use_playwright and PRECO_USAR_PLAYWRIGHT):
        return "", key
    if _commercial_signal_url(key) < 0.55 or _is_non_commercial_url(key):
        return "", key
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT, locale="pt-BR")
            page.goto(key, wait_until="domcontentloaded", timeout=PRICE_PLAYWRIGHT_TIMEOUT)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            html = page.content()
            final_url = page.url
            browser.close()
            _PRICE_HTTP_CACHE[key]=(html,final_url,time.time())
            return html, final_url
    except Exception as e:
        logger.warning("[PREÇO PLAYWRIGHT] %s", str(e)[:160])
        return "", key


def _buscar_preco_site(url_template: str, query: str) -> str:
    return url_template.format(query=quote_plus(query), q=quote_plus(query), termo=quote_plus(query))


def coletar_itens_preco_fonte(source: Dict[str, Any], query: str = "") -> List[PriceItem]:
    url = source.get("url", "")
    role = source.get("role", "competitor")
    name = source.get("name", "Fonte")
    location_note = str(source.get("location_note", ""))

    engine = os.getenv("EXTRACTION_ENGINE", EXTRACTION_ENGINE).strip().lower()
    if engine not in {"legacy", "generic", "shadow"}:
        engine = "legacy"

    # Se a fonte contiver arquivo ou payload de OCR bruto (folhetos, tablóides, encartes)
    ocr_origem = source.get("ocr_path") or source.get("ocr_json") or source.get("deteccoes")
    if ocr_origem:
        try:
            from extractors.bridge import executar_pipeline_extracao
            if engine == "generic":
                res = executar_pipeline_extracao(ocr_origem, engine="generic", source=name, role=role, page_url=url)
                return res.get("price_items", [])[:PRECO_MAX_OCR_ITENS_POR_PAGINA]
            elif engine == "shadow":
                res_leg = executar_pipeline_extracao(ocr_origem, engine="legacy", source=name, role=role, page_url=url)
                items_leg = res_leg.get("price_items", [])
                try:
                    res_gen = executar_pipeline_extracao(ocr_origem, engine="generic", source=name, role=role, page_url=url)
                    items_gen = res_gen.get("price_items", [])
                    logger.info("[SHADOW EXTRACT] %s -> Legacy: %d itens | Generic: %d itens", name, len(items_leg), len(items_gen))
                    try:
                        from extractors.canary import comparar_documento_canary
                        from extractors.canary_history import CanaryHistoryTracker, calcular_hash_conteudo_ou_arquivo
                        doc_rep = comparar_documento_canary(items_leg, items_gen, documento_id=str(ocr_origem))
                        h = calcular_hash_conteudo_ou_arquivo(ocr_origem)
                        tracker = CanaryHistoryTracker()
                        tracker.registrar_observacao(
                            run_id=f"shadow_{int(time.time())}",
                            document_id=Path(str(ocr_origem)).name if isinstance(ocr_origem, (str, Path)) else "payload",
                            document_hash=h,
                            source=name,
                            doc_report=doc_rep,
                            generic_crashed=False
                        )
                    except Exception as e_hist:
                        logger.debug("[SHADOW HISTORICO] %s", str(e_hist)[:100])
                except Exception as e_gen:
                    logger.warning("[SHADOW EXTRACT FALHA GENERIC] %s: %s", name, str(e_gen)[:120])
                    try:
                        from extractors.canary import CanaryDocumentReport
                        from extractors.canary_history import CanaryHistoryTracker, calcular_hash_conteudo_ou_arquivo
                        h = calcular_hash_conteudo_ou_arquivo(ocr_origem)
                        tracker = CanaryHistoryTracker()
                        tracker.registrar_observacao(
                            run_id=f"shadow_{int(time.time())}",
                            document_id=Path(str(ocr_origem)).name if isinstance(ocr_origem, (str, Path)) else "payload",
                            document_hash=h,
                            source=name,
                            doc_report=CanaryDocumentReport(documento_id=str(ocr_origem), total_legacy=len(items_leg)),
                            generic_crashed=True
                        )
                    except Exception:
                        pass
                return items_leg[:PRECO_MAX_OCR_ITENS_POR_PAGINA]
            else:
                res_leg = executar_pipeline_extracao(ocr_origem, engine="legacy", source=name, role=role, page_url=url)
                return res_leg.get("price_items", [])[:PRECO_MAX_OCR_ITENS_POR_PAGINA]
        except Exception as e:
            if engine == "generic":
                logger.error("[EXTRACTION GENERIC ERRO] %s: %s", name, str(e))
                raise
            logger.warning("[EXTRACTION OCR] %s", str(e)[:160])

    # Fluxo Web HTML padrão (LEGACY)
    if query and source.get("search_url"):
        url = _buscar_preco_site(str(source["search_url"]), query)
    if not url:
        return []
    if _is_blocked_price_domain(url):
        logger.info("[PREÇOS] fonte bloqueada/não comercial: %s", url)
        return []
    html, final_url = _price_page_html(url, use_playwright=True)
    if not html:
        logger.warning("[PREÇOS] sem HTML: %s", url)
        return []
    items = _extract_product_objects(html, name, role, final_url, location_note)
    if not items and not is_price_candidate_url(final_url) and PRICE_REQUIRE_COMMERCIAL_SIGNAL:
        logger.info("[PREÇOS] página sem sinais comerciais/produtos: %s", final_url)
        return []
    if query:
        for it in items:
            it.competitor = name
    return items[:PRECO_MAX_RESULTADOS_POR_BUSCA]


def _playwright_session_search(base_url: str, search_url_template: str, queries: List[str], location_hint: str = "") -> Dict[str, List[PriceItem]]:
    """Mantém uma única sessão Chromium por concorrente para preservar cookies/localização."""
    results: Dict[str, List[PriceItem]] = {}
    if not PRECO_USAR_PLAYWRIGHT:
        return results
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return results
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT, locale="pt-BR")
            page = context.new_page()
            page.goto(base_url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            page.wait_for_timeout(1000)
            base_text = page.locator("body").inner_text(timeout=12000) if page.locator("body") else ""
            location_confirmed = bool(CIDADE and normalizar(CIDADE) in normalizar(base_text))
            for query in queries:
                try:
                    target_url = _buscar_preco_site(search_url_template, query)
                    page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1200)
                    html = page.content()
                    final_url = page.url
                    note = location_hint
                    if location_confirmed:
                        note = (note + " | localização confirmada no contexto da sessão: " + CIDADE + ").").strip(" |")
                    items = _extract_product_objects(html, "", "competitor", final_url, note)
                    for item in items:
                        item.location_note = note
                    results[query] = items[:PRECO_MAX_RESULTADOS_POR_BUSCA]
                except Exception as e:
                    logger.warning("[PREÇOS SESSION] busca '%s': %s", query[:80], str(e)[:120])
                    results[query] = []
            browser.close()
    except Exception as e:
        logger.warning("[PREÇOS SESSION] falhou: %s", str(e)[:160])
    return results


def comparar_precos(fontes: List[Fonte], memoria: Optional[MemoriaSniper] = None, raw_results: Optional[List[Dict[str, Any]]] = None, tavily_client: Any = None) -> Dict[str, Any]:
    if not MONITORAR_PRECOS:
        return {"enabled": False, "reason": "monitoramento desativado"}
    sources=mesclar_price_sources(fontes, raw_results=raw_results, tavily_client=tavily_client)
    logger.info("[PREÇOS] fontes candidatas=%d | budget_fetches=%d", len(sources), PRICE_MAX_HTTP_FETCHES)
    for _src in sources[:12]:
        logger.info("[PREÇOS] candidato %s | %s | %s", _src.get("role"), _src.get("name"), _src.get("url"))
    targets=[x for x in sources if x.get("role")=="target"]
    competitors=[x for x in sources if x.get("role")=="competitor"]
    if not targets:
        logger.warning("[PREÇOS] nenhuma fonte comercial do alvo foi descoberta. Configure PRECO_ALVO_URLS/PRICE_SOURCES_JSON ou verifique buscas comerciais.")
        return {"enabled":True,"status":"sem_fonte_de_preco_do_alvo","comparacoes":[],"fontes_descobertas":sources}
    if not competitors:
        return {"enabled":True,"status":"sem_fontes_de_concorrentes","comparacoes":[],"fontes_descobertas":sources}
    item_cache: Dict[str,List[PriceItem]] = {}
    def cached_items(src: Dict[str, Any]) -> List[PriceItem]:
        key=f"{src.get('role','')}|{src.get('name','')}|{src.get('domain','')}|{src.get('url','')}"
        if key not in item_cache:
            item_cache[key]=coletar_itens_preco_fonte(src)
        return item_cache[key]
    # Deduplica por entidade/domínio e limita fontes para evitar crawler explosivo.
    def compact_sources(arr: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
        out=[]; seen=set()
        for x in sorted(arr,key=lambda s: _commercial_signal_url(s.get('url','')), reverse=True):
            k=(normalizar(x.get('name','')), source_domain_root(x.get('url','')), x.get('role',''))
            if not k[1] or k in seen: continue
            seen.add(k); out.append(x)
            if len([y for y in out if y.get('role')==x.get('role')])>=PRICE_MAX_DOMAINS_PER_ENTITY*max(1,len(CONCORRENTES)+1):
                break
        return out
    targets=compact_sources(targets)[:PRICE_MAX_DOMAINS_PER_ENTITY]
    competitors=compact_sources(competitors)
    target_items=[]
    for src in targets:
        target_items.extend(cached_items(src))
    uniq={}
    for it in target_items:
        if it.key(): uniq.setdefault(it.key(),it)
    target_items=[x for x in uniq.values() if getattr(x,"price_confidence",0.0)>=0.70]
    target_items=list(target_items)[:MAX_PRECO_ITENS]
    if not target_items:
        return {"enabled":True,"status":"sem_produtos_alvo","comparacoes":[],"produtos_alvo":0,"fontes_descobertas":sources}
    comparacoes=[]
    for comp in competitors:
        catalog=cached_items(comp)
        search_template=str(comp.get("search_url","")).strip()
        session_results={}
        queries=[" ".join(x for x in [t.brand,t.name,t.unit] if x).strip() for t in target_items[:MAX_BUSCAS_PRECO_CONCORRENTE]] if search_template else []
        if search_template and PRECO_USAR_PLAYWRIGHT:
            session_results=_playwright_session_search(str(comp.get("url","")),search_template,queries,str(comp.get("location_note","")))
        for target in target_items[:MAX_BUSCAS_PRECO_CONCORRENTE]:
            q=" ".join(x for x in [target.brand,target.name,target.unit] if x).strip()
            results=list(catalog)
            if session_results.get(q): results.extend(session_results[q])
            if not results and search_template: results=coletar_itens_preco_fonte(comp,q)
            if not results:
                comparacoes.append({"produto_alvo":target.name,"marca":target.brand,"unidade":target.unit,"alvo_preco":target.price,"alvo_promocao":target.promotion,"concorrente":comp.get("name",""),"concorrente_produto":"","concorrente_preco":None,"similaridade":0.0,"dif_percent":None,"mais_barato":"não encontrado","confianca_match":"baixa","url_alvo":target.url,"url_concorrente":comp.get("url",""),"location_note":comp.get("location_note","")})
                continue
            results=[r for r in results if getattr(r,"price_confidence",0.0)>=0.70 and _price_page_type(r.url,getattr(r,"page_type",""),r.name) not in {"BLOCKED","ARTICLE_OR_EMPLOYMENT"}]
            if not results:
                comparacoes.append({"produto_alvo":target.name,"marca":target.brand,"unidade":target.unit,"alvo_preco":target.price,"alvo_promocao":target.promotion,"concorrente":comp.get("name",""),"concorrente_produto":"","concorrente_preco":None,"similaridade":0.0,"match_class":"nao_encontrado","dif_percent":None,"mais_barato":"não encontrado","confianca_match":"baixa","url_alvo":target.url,"url_concorrente":comp.get("url",""),"location_note":comp.get("location_note","")})
                continue
            ranked=sorted(((similaridade_produto(target,r),r) for r in results),key=lambda x:x[0],reverse=True)
            sim,best=ranked[0]
            row={"produto_alvo":target.name,"marca":target.brand,"unidade":target.unit,"alvo_preco":target.price,"alvo_old_price":target.old_price,"alvo_promocao":target.promotion,"concorrente":comp.get("name",""),"concorrente_produto":best.name,"concorrente_preco":best.price,"concorrente_old_price":best.old_price,"concorrente_promocao":best.promotion,"similaridade":round(sim,3),"url_alvo":target.url,"url_concorrente":best.url,"location_note":best.location_note or comp.get("location_note",""),"canonical_product_id":sha1(normalizar(f"{target.brand}|{target.name}|{target.unit}|{target.sku}"))[:24]}
            if sim>=PRECO_MIN_SIMILARIDADE and target.price and best.price:
                row["dif_percent"]=round((best.price-target.price)/target.price*100,2)
                if abs(row["dif_percent"]) > 300:
                    row["dif_percent"]=None
                    row["mais_barato"]="não comparável"
                    row["match_class"]="revisao_necessaria"
                    row["confianca_match"]="baixa"
                else:
                    row["mais_barato"]="concorrente" if best.price<target.price else "alvo" if target.price<best.price else "igual"
                    row["match_class"]="confirmado" if sim>=0.90 else "provavel"
                    row["confianca_match"]="alta" if sim>=0.88 else "media"
            else:
                row["dif_percent"]=None; row["mais_barato"]="não comparável"; row["match_class"]="nao_comparavel"; row["confianca_match"]="baixa"
            comparacoes.append(row)
    snapshots=[]
    for src in targets+competitors:
        entity=str(src.get("name") or "")
        role=str(src.get("role") or "")
        items=cached_items(src)
        for it in items:
            snapshots.append({"entity":entity,"role":role,"source_domain":dominio(it.url or src.get("url","")),"product_key":it.key(),"product_name":it.name,"brand":it.brand,"unit":it.unit,"price":it.price,"old_price":it.old_price,"promotion":it.promotion,"url":it.url,"location_note":it.location_note})
    history=memoria.save_price_snapshots(RUN_ID,snapshots) if memoria else {"previous_run":None,"gravados":0,"mudancas":[]}
    comparable=[x for x in comparacoes if x.get("dif_percent") is not None]
    by_comp={}
    for row in comparable: by_comp.setdefault(row["concorrente"],[]).append(row)
    guerra=[]
    for comp, rows in by_comp.items():
        ds=[r["dif_percent"] for r in rows]
        guerra.append({"concorrente":comp,"comparaveis":len(rows),"concorrente_mais_barato":sum(r["mais_barato"]=="concorrente" for r in rows),"alvo_mais_barato":sum(r["mais_barato"]=="alvo" for r in rows),"empates":sum(r["mais_barato"]=="igual" for r in rows),"dif_media_percent":round(sum(ds)/len(ds),2),"dif_mediana_percent":round(sorted(ds)[len(ds)//2],2),"maior_gap_percent":round(max(ds,key=lambda z:abs(z)),2)})
    guerra.sort(key=lambda x:(x["concorrente_mais_barato"],abs(x["dif_media_percent"])),reverse=True)
    return {"enabled":True,"status":"ok" if comparable else "sem_matches_confiaveis","produtos_alvo":len(target_items),"comparacoes":comparacoes,"comparaveis":len(comparable),"alvo_mais_barato":sum(x["mais_barato"]=="alvo" for x in comparable),"concorrente_mais_barato":sum(x["mais_barato"]=="concorrente" for x in comparable),"promocoes_alvo":sum(bool(x.get("alvo_promocao")) for x in comparacoes),"promocoes_concorrentes":sum(bool(x.get("concorrente_promocao")) for x in comparacoes),"maiores_gaps":sorted(comparable,key=lambda x:abs(x.get("dif_percent",0)),reverse=True)[:15],"fontes":sources,"guerra_de_precos":guerra,"historico":history,"snapshots_observados":len(snapshots),"metodologia":"descoberta automática de domínios comerciais + expansão de homepage/sitemap/links comerciais; catálogo direto e pesquisa por produto quando disponível; matching por nome/marca/unidade; somente matches acima do limiar entram na comparação; snapshots persistidos em SQLite para histórico de guerra de preços."}


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
# 9. MOTOR DE EVENTOS, SINAIS E SCORES
# ============================================================

def recencia_score(f: Fonte, hoje: Optional[datetime] = None) -> float:
    return _domain_recencia_score(f, hoje or HOJE)


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


def medir_dimensoes(fontes: List[Fonte], events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return _domain_medir_dimensoes(fontes, events)


def score_ambiente_competitivo(dimensoes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return _domain_score_ambiente_competitivo(dimensoes)


def score_pressao_competitiva(fontes: List[Fonte], events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _domain_score_pressao_competitiva(fontes, events, empresa_alvo=EMPRESA_ALVO)


def score_vulnerabilidade_empresa(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _domain_score_vulnerabilidade_empresa(events, empresa_alvo=EMPRESA_ALVO)


def classificar_sinal(event: Dict[str, Any]) -> str:
    return _domain_classificar_sinal(event)


def acao_evento(kind: str) -> str:
    return _domain_acao_evento(kind)


def gerar_sinais_deterministicos(fontes: List[Fonte], events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _domain_gerar_sinais_deterministicos(fontes, events)


def score_momentum(events: List[Dict[str, Any]], fontes: List[Fonte]) -> int:
    return _domain_score_momentum(events, fontes, hoje=HOJE)

# ============================================================
# 10. LLM ESTRUTURADO (OPCIONAL)
# ============================================================

client_groq = None
client_gemini = None
if CHAVE_GROQ and Groq:
    try:
        client_groq = Groq(api_key=CHAVE_GROQ)
    except Exception:
        pass
if GEMINI_API_KEY and genai:
    try:
        client_gemini = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass

CACHE: Dict[str, Tuple[str, float]] = {}
CACHE_TTL = 21600

SYSTEM_PROMPT = f"""
Você é o motor de inteligência competitiva do Agente Sniper.
Empresa: {EMPRESA_ALVO}
Nicho: {NICHO}
Local: {CIDADE}-{ESTADO}

Você recebe evidências previamente coletadas. Não navegue, não invente fatos.
Separe FATO de INFERÊNCIA ESTRATÉGICA. Nunca trate ausência de evidência como ausência.
Toda afirmação factual precisa indicar evidence_ids. Não invente IDs.
Seu trabalho é responder: o que mudou, por que importa, qual risco existe,
qual oportunidade existe e que decisão deveria ser considerada.
"""


def chamar_ollama(prompt: str) -> Optional[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=4)
        if r.status_code >= 400:
            return None
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODELO, "prompt": SYSTEM_PROMPT + "\n\n" + prompt, "stream": False, "format": "json"},
            timeout=180,
        )
        r.raise_for_status()
        return str(r.json().get("response", "")).strip() or None
    except Exception:
        return None


def chamar_gemini(prompt: str) -> Optional[str]:
    if not client_gemini or not genai_types:
        return None
    for model in GEMINI_MODELOS:
        try:
            cfg = genai_types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, max_output_tokens=5000)
            r = client_gemini.models.generate_content(model=model, contents=prompt, config=cfg)
            txt = (getattr(r, "text", "") or "").strip()
            if txt:
                return txt
        except Exception as e:
            logger.warning("[GEMINI] %s: %s", model, str(e)[:120])
    return None


def chamar_groq(prompt: str) -> Optional[str]:
    if not USAR_GROQ or not client_groq:
        return None
    for model in GROQ_MODELOS:
        try:
            kwargs: Dict[str, Any] = {
                "model": model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 5000,
            }
            # JSON Object Mode é suportado por alguns modelos; usamos somente quando solicitado pelo ambiente.
            if os.getenv("GROQ_JSON_MODE", "1") == "1":
                kwargs["response_format"] = {"type": "json_object"}
            r = client_groq.chat.completions.create(**kwargs)
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                return txt
        except Exception as e:
            logger.warning("[GROQ] %s: %s", model, str(e)[:120])
    return None


def chamar_llm_json(prompt: str) -> Optional[Dict[str, Any]]:
    key = sha1(SYSTEM_PROMPT + prompt)
    cached = CACHE.get(key)
    if cached and time.time() - cached[1] < CACHE_TTL:
        return json_seguro(cached[0])
    fornecedores = []
    if os.getenv("USAR_OLLAMA", "1") == "1":
        fornecedores.append(("ollama", chamar_ollama))
    fornecedores += [("gemini", chamar_gemini)]
    if USAR_GROQ:
        fornecedores.append(("groq", chamar_groq))
    for nome, fn in fornecedores:
        try:
            result = fn(prompt)
            obj = json_seguro(result or "")
            if obj:
                CACHE[key] = (result or "", time.time())
                logger.info("[IA] %s respondeu JSON", nome)
                return obj
        except Exception as e:
            logger.warning("[IA] %s falhou: %s", nome, str(e)[:140])
    return None


def gerar_inteligencia_llm(fontes: List[Fonte], events: List[Dict[str, Any]], ambiente: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    evidencias = []
    for f in sorted(fontes, key=lambda x: x.score, reverse=True)[:36]:
        evidencias.append({
            "id": f.id,
            "titulo": truncar(f.titulo, 180),
            "url": f.url,
            "categoria": f.categoria,
            "data": f.data_publicacao,
            "atual": f.atual,
            "escopo": f.escopo,
            "score": round(f.score, 1),
            "confianca": round(f.confianca, 2),
            "trecho": truncar(f.resumo_busca or f.conteudo, 650),
        })
    prompt = f"""
RETORNE SOMENTE JSON VÁLIDO. Você é o estrategista de inteligência competitiva do Agente Sniper.
Empresa: {EMPRESA_ALVO}
Nicho: {NICHO}
Local: {CIDADE}-{ESTADO}

OBJETIVO:
Transformar fatos públicos em decisões úteis. Não invente fatos.
Uma ação estratégica pode ser uma inferência, mas deve estar claramente apoiada por evidence_ids.
Nunca trate uma única reclamação como problema estrutural.
Nunca use uma fonte sem data como se fosse evidência recente.
Nunca conte a mesma fonte como várias evidências independentes.
Não trate diretório/catálogo como prova de desempenho, preço real ou crescimento.
Não use fonte corporativa para afirmar desempenho local sem evidência local.
Não invente concorrentes: use apenas concorrentes configurados ou explicitamente identificados nas evidências. Um evento da própria empresa não pode ser descrito como movimento de um concorrente.

SCHEMA:
{{
  "resumo_executivo": ["..."],
  "sinais": [
    {{"titulo":"...","tipo":"RISCO|OPORTUNIDADE|MOVIMENTO","impacto":"BAIXO|MEDIO|ALTO","urgencia":"BAIXA|MEDIA|ALTA","racional":"...","acao":"...","evidence_ids":[1],"confianca":0.0,"limite":"..."}}
  ],
  "concorrencia": [
    {{"nome":"...","movimento":"...","confianca":0.0,"evidence_ids":[1]}}
  ],
  "prioridades_30": ["..."],
  "prioridades_60": ["..."],
  "prioridades_90": ["..."],
  "lacunas": ["..."]
}}

ÍNDICES PRELIMINARES:
- atividade da empresa: ambiente_competitivo.score
- pressão competitiva externa: pressao_competitiva.score (pode ser nulo)
- vulnerabilidade da empresa: vulnerabilidade_empresa.score
- momentum do mercado: momentum_mercado

{json.dumps(ambiente, ensure_ascii=False)}

EVENTOS CANÔNICOS:
Cada event_id representa um fato. Não crie eventos adicionais a partir das mesmas evidências.
{json.dumps(events[:36], ensure_ascii=False)}

EVIDÊNCIAS:
{json.dumps(evidencias, ensure_ascii=False)}
"""
    obj = chamar_llm_json(prompt)
    if not obj:
        return None
    ids_validos = {f.id for f in fontes}
    for item in obj.get("sinais", []) or []:
        if isinstance(item, dict):
            item["evidence_ids"] = [int(x) for x in item.get("evidence_ids", []) if str(x).isdigit() and int(x) in ids_validos]
    for item in obj.get("concorrencia", []) or []:
        if isinstance(item, dict):
            item["evidence_ids"] = [int(x) for x in item.get("evidence_ids", []) if str(x).isdigit() and int(x) in ids_validos]
    return obj

# ============================================================
# 11. MOTOR DE DECISÃO
# ============================================================

def inteligencia_deterministica(fontes: List[Fonte], events: List[Dict[str, Any]], ambiente: Dict[str, Any]) -> Dict[str, Any]:
    sinais = gerar_sinais_deterministicos(fontes, events)
    dims = ambiente.get("dimensoes", {})
    melhor_dim = sorted(dims.items(), key=lambda kv: kv[1].get("score", 0), reverse=True)
    lacunas = []
    if dims.get("PREÇO", {}).get("score", 0) < 35:
        lacunas.append("Não há comparação confiável de preço suficiente nesta execução.")
    if dims.get("REPUTAÇÃO", {}).get("score", 0) < 35:
        lacunas.append("Não há amostra suficiente para inferir tendência de reputação.")
    if dims.get("EXPANSÃO", {}).get("score", 0) < 35:
        lacunas.append("Não há evidência suficiente de expansão recente.")
    if not any(e.get("date") for e in events):
        lacunas.append("A maior parte das evidências não possui data verificável.")
    top = melhor_dim[0][0] if melhor_dim else "dados insuficientes"
    pc = ambiente.get("pressao_competitiva", {})
    vb = ambiente.get("vulnerabilidade_empresa", {})
    resumo = [
        f"O radar identificou {len(fontes)} evidências válidas e {len(events)} eventos canônicos, agrupando múltiplas fontes do mesmo fato.",
        f"A atividade observável da empresa está em {ambiente['score']}/100 ({ambiente['label']}) e a vulnerabilidade externa/operacional estimada está em {vb.get('score',0)}/100 ({vb.get('label','BAIXA')}).",
        (f"A pressão competitiva externa está em {pc.get('score')}/100 ({pc.get('label')})." if pc.get('score') is not None else "A pressão competitiva externa não foi calculada por falta de evidência independente suficiente."),
        f"A dimensão com maior sinal nesta execução é {top}; isso representa atenção de monitoramento, não prova automática de perda financeira.",
    ]
    return {
        "resumo_executivo": resumo,
        "sinais": sinais,
        "concorrencia": [],
        "prioridades_30": [
            "Validar os 3 sinais de maior impacto com dados internos e contexto operacional.",
            "Definir concorrentes prioritários e iniciar uma linha de base comparativa.",
        ],
        "prioridades_60": [
            "Comparar tendência de preço, reputação, produto/serviço e movimento dos concorrentes.",
            "Transformar o principal sinal em um teste mensurável.",
        ],
        "prioridades_90": [
            "Consolidar indicadores em rotina semanal de decisão e alertas.",
            "Recalibrar scores com resultados observados na execução anterior.",
        ],
        "lacunas": lacunas or ["Não foram detectadas lacunas críticas nas dimensões monitoradas."],
    }

# ============================================================
# 12. VALIDAÇÃO DE EVIDÊNCIAS
# ============================================================

def validar_ids_sinais(pacote: Dict[str, Any], ids_validos: set) -> Tuple[bool, str]:
    invalidos = []
    for campo in ("sinais", "concorrencia"):
        for item in pacote.get(campo, []) or []:
            if not isinstance(item, dict):
                continue
            for x in item.get("evidence_ids", []) or []:
                if str(x).isdigit() and int(x) not in ids_validos:
                    invalidos.append(int(x))
    if invalidos:
        return False, f"IDs inválidos: {sorted(set(invalidos))}"
    return True, "ok"


def validar_pacote(pacote: Dict[str, Any], fontes: List[Fonte]) -> Dict[str, Any]:
    ids = {f.id for f in fontes}
    ok, reason = validar_ids_sinais(pacote, ids)
    sinais_validos = []
    for s in pacote.get("sinais", []) or []:
        if not isinstance(s, dict):
            continue
        refs = [int(x) for x in s.get("evidence_ids", []) if str(x).isdigit() and int(x) in ids]
        if refs:
            # Confiança não pode superar a melhor confiança das evidências.
            max_conf = max((fontes[i-1].confianca for i in refs if 0 < i <= len(fontes)), default=0.0)
            try:
                s["confianca"] = min(float(s.get("confianca", max_conf)), max_conf)
            except Exception:
                s["confianca"] = max_conf
            s["evidence_ids"] = sorted(set(refs))
            sinais_validos.append(s)
    pacote["sinais"] = sinais_validos
    concorrentes_validos = []
    corpus = " ".join(f.texto() for f in fontes).lower()
    for c in pacote.get("concorrencia", []) or []:
        if not isinstance(c, dict):
            continue
        nome = str(c.get("nome", "")).strip()
        refs = [int(x) for x in c.get("evidence_ids", []) if str(x).isdigit() and int(x) in ids]
        if not nome or not refs:
            continue
        if normalizar(nome) in normalizar(corpus):
            c["evidence_ids"] = sorted(set(refs))
            concorrentes_validos.append(c)
    pacote["concorrencia"] = concorrentes_validos
    return {
        "valido": ok and bool(sinais_validos),
        "sinais": len(sinais_validos),
        "motivo": reason,
        "ids_validos": len(ids),
    }

# ============================================================
# 13. RENDERIZAÇÃO EXECUTIVA
# ============================================================

def ref_text(ids: Sequence[int]) -> str:
    return " ".join(f"[FONTE {int(x)}]" for x in ids)


def fonte_por_id(fontes: List[Fonte]) -> Dict[int, Fonte]:
    return {f.id: f for f in fontes}


def html_escape(s: Any) -> str:
    import html
    return html.escape(str(s or ""))


def rotulo_dimensao(k: str) -> str:
    return k.title().replace("Serviço", "Serviço")


def gerar_html(pacote: Dict[str, Any], fontes: List[Fonte], events: List[Dict[str, Any]], ambiente: Dict[str, Any], memoria: Dict[str, Any]) -> str:
    fmap = fonte_por_id(fontes)
    sinais = pacote.get("sinais", [])[:8]
    resumo = pacote.get("resumo_executivo", [])[:5]
    dims = ambiente.get("dimensoes", {})
    concorrencia = pacote.get("concorrencia", [])[:8]
    score = ambiente["score"]
    cor_score = "bad" if score >= 70 else "warn" if score >= 45 else "good"
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Agente Sniper — {html_escape(EMPRESA_ALVO)}</title>
<style>
:root{{--bg:#f4f6fa;--ink:#17212b;--muted:#667487;--card:#fff;--line:#e4e9ef;--navy:#0b1d33;--blue:#1e5eff;--red:#c62828;--orange:#a86200;--green:#147a45}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}} .wrap{{max-width:1240px;margin:auto;padding:24px}}
.hero{{background:linear-gradient(135deg,#091522,#173c63);color:#fff;border-radius:24px;padding:32px;box-shadow:0 16px 40px rgba(5,20,40,.18)}} .kicker{{font-size:11px;letter-spacing:.16em;text-transform:uppercase;opacity:.74}} h1{{font-size:38px;margin:10px 0 4px}} .sub{{opacity:.86}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:16px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 6px 20px rgba(24,33,43,.05)}} .metric{{font-size:30px;font-weight:850}} .label{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}
.section{{margin-top:28px}} h2{{font-size:21px;margin:0 0 12px}} .lead{{font-size:15px;line-height:1.55}} .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.score{{border-radius:18px;padding:16px;background:#fff;border:1px solid var(--line)}} .scorebar{{height:10px;background:#edf1f5;border-radius:99px;overflow:hidden;margin-top:9px}} .scorefill{{height:100%}} .fillgood{{background:var(--green)}} .fillwarn{{background:#d28a10}} .fillbad{{background:var(--red)}}
.signal{{background:#fff;border:1px solid var(--line);border-left:5px solid var(--blue);border-radius:16px;padding:16px;margin:10px 0}} .risk{{border-left-color:var(--red)}} .opp{{border-left-color:var(--green)}} .move{{border-left-color:#c48a15}} .pill{{display:inline-block;padding:5px 8px;border-radius:999px;background:#eef2f7;font-size:10px;font-weight:800;margin-right:5px}} .muted{{color:var(--muted);font-size:12px}} .action{{font-weight:700;margin-top:8px}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:16px;overflow:hidden}} th,td{{padding:11px;border-bottom:1px solid #edf1f4;text-align:left;font-size:12px}} th{{background:#f7f9fb;color:#506072}} .source{{margin:10px 0;padding:11px;border-bottom:1px solid #edf1f4}} .source a{{color:#1e5eff;text-decoration:none;word-break:break-all}} .footer{{margin-top:28px;color:var(--muted);font-size:11px}}
@media(max-width:900px){{.grid{{grid-template-columns:repeat(2,1fr)}}.grid2{{grid-template-columns:1fr}}}} @media(max-width:560px){{.grid{{grid-template-columns:1fr}}.wrap{{padding:12px}}h1{{font-size:28px}}}}
</style></head><body><div class='wrap'>
<div class='hero'><div class='kicker'>AGENTE SNIPER · RADAR DE INTELIGÊNCIA COMPETITIVA v{APP_VERSION}</div><h1>{html_escape(EMPRESA_ALVO)}</h1><div class='sub'>{html_escape(CIDADE)}-{html_escape(ESTADO)} · {html_escape(PROFILE['label'])} · {HOJE.strftime('%d/%m/%Y %H:%M')}</div></div>
<div class='grid'>
<div class='card'><div class='label'>Pressão competitiva</div><div class='metric'>{('—' if ambiente.get('pressao_competitiva',{}).get('score') is None else str(ambiente['pressao_competitiva']['score'])+'/100')}</div><div>{html_escape(ambiente.get('pressao_competitiva',{}).get('label','NÃO CALCULADO'))}</div></div>
<div class='card'><div class='label'>Vulnerabilidade</div><div class='metric'>{ambiente.get('vulnerabilidade_empresa',{}).get('score',0)}/100</div><div>{html_escape(ambiente.get('vulnerabilidade_empresa',{}).get('label','BAIXA'))}</div></div>
<div class='card'><div class='label'>Momentum do mercado</div><div class='metric'>{ambiente.get('momentum_mercado',0)}/100</div><div>movimentos recentes datados</div></div>
<div class='card'><div class='label'>Eventos canônicos</div><div class='metric'>{len(events)}</div><div>{len(fontes)} evidências auditáveis · {memoria.get('novas_fontes',0)} novas</div></div></div>
<div class='section'><h2>Decisão em 15 minutos</h2><div class='grid2'><div class='card lead'>{''.join('<p>'+html_escape(x)+'</p>' for x in resumo)}</div>
<div class='score'><div class='label'>Cobertura do radar</div><div class='metric'>{int(ambiente.get('cobertura',0)*100)}%</div><div class='muted'>quanto das dimensões tem evidência suficiente para influenciar o índice</div><div class='scorebar'><div class='scorefill fill{cor_score}' style='width:{int(ambiente.get('cobertura',0)*100)}%'></div></div></div></div></div>
<div class='section'><h2>Onde está a pressão</h2><div class='card lead'><b>Leitura dos índices:</b> pressão competitiva mede movimentos externos; vulnerabilidade mede sinais de risco da empresa monitorada; momentum mede velocidade de movimentos recentes. Eles não são equivalentes.</div><div class='grid2'>"""
    for k, d in sorted(dims.items(), key=lambda kv: kv[1].get("score",0), reverse=True):
        s=d.get("score",0); cl="bad" if s>=70 else "warn" if s>=45 else "good"
        html += f"<div class='score'><div class='label'>{html_escape(rotulo_dimensao(k))}</div><div class='metric'>{s}/100</div><div class='muted'>{d.get('eventos',0)} eventos · {d.get('evidencias',0)} evidências · {d.get('eventos_correlacionados',0)} corroborados</div><div class='scorebar'><div class='scorefill fill{cl}' style='width:{s}%'></div></div></div>"
    html += "</div></div>"
    cp = pacote.get("comparacao_precos", {})
    if cp.get("enabled"):
        html += "<div class='section'><h2>Comparador de preços e promoções</h2>"
        html += "<div class='card lead'><b>Status:</b> " + html_escape(str(cp.get("status", ""))) + " · <b>Produtos-base:</b> " + str(cp.get("produtos_alvo", 0)) + " · <b>Comparáveis:</b> " + str(cp.get("comparaveis", 0)) + "</div>"
        html += "<div class='grid2'>"
        for x in cp.get("maiores_gaps", [])[:6]:
            dp = x.get("dif_percent")
            sinal = "concorrente mais barato" if dp is not None and dp < 0 else "alvo mais barato" if dp is not None and dp > 0 else "sem diferença"
            html += f"<div class='score'><div class='label'>{html_escape(x.get('produto_alvo',''))}</div><div class='metric'>{'—' if dp is None else f'{dp:+.1f}%'} </div><div>{html_escape(sinal)}</div><div class='muted'>{html_escape(x.get('concorrente',''))} · match {int(float(x.get('similaridade',0))*100)}% · {html_escape(x.get('location_note',''))}</div></div>"
        html += "</div><div class='card lead'><b>Promoções:</b> alvo " + str(cp.get("promocoes_alvo", 0)) + " · concorrentes " + str(cp.get("promocoes_concorrentes", 0)) + "</div></div>"
        html += "<div class='section'><h3>Guerra de preços — histórico</h3>"
        html += "<div class='card lead'><b>Snapshots:</b> " + str(cp.get("snapshots_observados", 0)) + " · <b>Mudanças desde a última execução:</b> " + str(len(cp.get("historico", {}).get("mudancas", []))) + "</div>"
        if cp.get("guerra_de_precos"):
            html += "<table><thead><tr><th>Concorrente</th><th>Comparáveis</th><th>Concorrente mais barato</th><th>Alvo mais barato</th><th>Diferença média</th></tr></thead><tbody>"
            for g in cp.get("guerra_de_precos", [])[:10]:
                html += f"<tr><td>{html_escape(g.get('concorrente'))}</td><td>{g.get('comparaveis',0)}</td><td>{g.get('concorrente_mais_barato',0)}</td><td>{g.get('alvo_mais_barato',0)}</td><td>{g.get('dif_media_percent',0)}%</td></tr>"
            html += "</tbody></table>"
        for ch in cp.get("historico", {}).get("mudancas", [])[:12]:
            sinal="subiu" if float(ch.get("change_pct") or 0)>0 else "caiu"
            html += f"<div class='source'><b>{html_escape(ch.get('entity'))}</b> — {html_escape(ch.get('product_name'))}: {sinal} {abs(float(ch.get('change_pct') or 0)):.1f}% · R$ {float(ch.get('previous_price') or 0):.2f} → R$ {float(ch.get('current_price') or 0):.2f}</div>"
        html += "</div>"
    html += "<div class='section'><h2>Sinais que merecem decisão</h2>"
    for s in sinais:
        typ=str(s.get('tipo','MOVIMENTO')).upper(); cls='risk' if typ=='RISCO' else 'opp' if typ=='OPORTUNIDADE' else 'move'; refs=[x for x in s.get('evidence_ids',[]) if x in fmap]
        html += f"<div class='signal {cls}'><span class='pill'>{html_escape(typ)}</span><span class='pill'>{html_escape(s.get('impacto'))}</span><span class='pill'>{html_escape(s.get('urgencia'))}</span><h3>{html_escape(s.get('titulo'))}</h3><div class='muted'>{html_escape(s.get('limite'))} · confiança {int(float(s.get('confianca',0))*100)}%</div><p>{html_escape(s.get('racional'))}</p><p class='action'>AÇÃO: {html_escape(s.get('acao'))}</p><div class='muted'>Evidência: {html_escape(ref_text(refs))}</div></div>"
    html += "</div>"
    html += "<div class='section'><h2>Radar de concorrência</h2>"
    if concorrencia:
        html += "<table><thead><tr><th>Concorrente</th><th>Movimento</th><th>Confiança</th><th>Evidência</th></tr></thead><tbody>"
        for c in concorrencia:
            html += f"<tr><td>{html_escape(c.get('nome'))}</td><td>{html_escape(c.get('movimento'))}</td><td>{int(float(c.get('confianca',0))*100)}%</td><td>{html_escape(ref_text(c.get('evidence_ids',[])))}</td></tr>"
        html += "</tbody></table>"
    else:
        html += "<div class='card'><b>Ainda não há concorrentes suficientemente identificados nesta execução.</b><p class='muted'>Configure CONCORRENTES ou aumente a coleta específica de mercado antes de tomar decisões ofensivas.</p></div>"
    html += "</div><div class='section'><h2>Plano 30 / 60 / 90 dias</h2><div class='grid2'>"
    for label, arr in [("30 dias",pacote.get('prioridades_30',[])),("60 dias",pacote.get('prioridades_60',[])),("90 dias",pacote.get('prioridades_90',[]))]:
        html += f"<div class='card'><div class='label'>{label}</div>{''.join('<p>• '+html_escape(x)+'</p>' for x in arr[:5])}</div>"
    html += "</div></div><div class='section'><h2>Lacunas de informação</h2><div class='card'>" + ''.join(f"<p>• {html_escape(x)}</p>" for x in pacote.get('lacunas',[])) + "</div></div>"
    html += "<div class='section'><h2>Eventos mais relevantes</h2>"
    for e in events[:15]:
        html += f"<div class='source'><b>{html_escape(e['kind'])}</b> — {html_escape(e['title'])}<div class='muted'>{e['importance']}/100 · confiança {int(float(e.get('confidence',0))*100)}% · {e.get('independent_source_count',1)} fonte(s) independente(s) · {html_escape(e.get('date') or 'data não identificada')} · {html_escape(ref_text(e.get('evidence_ids',[])))}</div></div>"
    html += "</div><div class='section'><h2>Evidências auditáveis</h2><table><thead><tr><th>ID</th><th>Escopo</th><th>Data</th><th>Fonte</th><th>Título</th><th>Score</th></tr></thead><tbody>"
    for f in fontes[:80]:
        html += f"<tr><td>{f.id}</td><td>{html_escape(f.escopo)}</td><td>{html_escape(f.data_publicacao or 'não identificada')}</td><td>{html_escape(f.dominio)}</td><td>{html_escape(f.titulo)}</td><td>{f.score:.1f}</td></tr>"
    html += "</tbody></table></div><div class='footer'>Agente Sniper v"+APP_VERSION+". Fatos devem ser interpretados junto das evidências referenciadas. Um sinal não é prova de causalidade financeira.</div></div></body></html>"
    return html


def gerar_pdf(pacote: Dict[str, Any], fontes: List[Fonte], events: List[Dict[str, Any]], ambiente: Dict[str, Any], memoria: Dict[str, Any]) -> Optional[str]:
    if not FPDF:
        return None
    try:
        pdf=FPDF(); pdf.set_auto_page_break(True,14); pdf.add_page()
        pdf.set_fill_color(9,21,34); pdf.rect(0,0,210,48,"F")
        pdf.set_text_color(255,255,255); pdf.set_font("Helvetica","B",22); pdf.set_y(9)
        pdf.cell(0,10,"AGENTE SNIPER",new_x=XPos.LMARGIN,new_y=YPos.NEXT,align="C")
        pdf.set_font("Helvetica","B",15); pdf.cell(0,8,remover_acentos(EMPRESA_ALVO),new_x=XPos.LMARGIN,new_y=YPos.NEXT,align="C")
        pdf.set_font("Helvetica","",9); pdf.cell(0,6,remover_acentos(f"Radar competitivo | {CIDADE}-{ESTADO} | {HOJE.strftime('%d/%m/%Y %H:%M')}"),new_x=XPos.LMARGIN,new_y=YPos.NEXT,align="C")
        pdf.set_y(58); pdf.set_text_color(20,30,40); pdf.set_font("Helvetica","B",17); pp=ambiente.get("pressao_competitiva",{}); pp_text="Pressao competitiva: nao calculada" if pp.get("score") is None else f"Pressao competitiva: {pp.get("score")}/100 ({pp.get("label")})"; pdf.cell(0,9,remover_acentos(pp_text),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        pdf.set_font("Helvetica","",10); pdf.multi_cell(0,5,remover_acentos("Este relatório separa evidência, evento, interpretação e decisão. Scores não representam impacto financeiro sem dados internos."),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        cp = pacote.get("comparacao_precos", {})
        if cp.get("enabled"):
            pdf.add_page(); pdf.set_text_color(19,67,110); pdf.set_font("Helvetica","B",15); pdf.cell(0,9,remover_acentos("COMPARADOR DE PREÇOS E PROMOÇÕES"),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            pdf.set_text_color(25,35,45); pdf.set_font("Helvetica","",9)
            pdf.multi_cell(0,5,remover_acentos(f"Status: {cp.get('status','')} | Produtos-base: {cp.get('produtos_alvo',0)} | Comparáveis: {cp.get('comparaveis',0)}"),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            for x in cp.get("maiores_gaps", [])[:10]:
                dp = x.get("dif_percent")
                txt = f"{x.get('produto_alvo','')} | {x.get('concorrente','')} | alvo R$ {x.get('alvo_preco','—')} | concorrente R$ {x.get('concorrente_preco','—')} | diferença {('—' if dp is None else f'{dp:+.1f}%')} | match {int(float(x.get('similaridade',0))*100)}%"
                pdf.multi_cell(0,5,remover_acentos(txt),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            pdf.ln(3)
            pdf.multi_cell(0,5,remover_acentos(f"Promoções detectadas: alvo {cp.get('promocoes_alvo',0)} | concorrentes {cp.get('promocoes_concorrentes',0)}. Preços sem correspondência confiável não entram no ranking."),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        for title, content in [("RESUMO EXECUTIVO",pacote.get('resumo_executivo',[])),("SINAIS DE DECISÃO",pacote.get('sinais',[])),("RADAR DE DIMENSÕES",[]),("RADAR DE EVENTOS",events[:25]),("PLANO 30 / 60 / 90 DIAS",None)]:
            pdf.add_page(); pdf.set_text_color(19,67,110); pdf.set_font("Helvetica","B",15); pdf.cell(0,9,remover_acentos(title),new_x=XPos.LMARGIN,new_y=YPos.NEXT); pdf.set_text_color(25,35,45)
            if title=="RADAR DE DIMENSÕES":
                pdf.set_font("Helvetica","",9)
                for k,d in sorted(ambiente.get('dimensoes',{}).items(), key=lambda kv:kv[1].get('score',0), reverse=True):
                    pdf.multi_cell(0,5,remover_acentos(f"{k}: {d.get('score',0)}/100 | {d.get('eventos',0)} eventos | {d.get('evidencias',0)} evidencias"),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            elif title=="PLANO 30 / 60 / 90 DIAS":
                pdf.set_font("Helvetica","",9)
                for lab,arr in [("30 DIAS",pacote.get('prioridades_30',[])),("60 DIAS",pacote.get('prioridades_60',[])),("90 DIAS",pacote.get('prioridades_90',[]))]:
                    pdf.set_font("Helvetica","B",10); pdf.cell(0,7,lab,new_x=XPos.LMARGIN,new_y=YPos.NEXT); pdf.set_font("Helvetica","",9)
                    for x in arr[:6]: pdf.multi_cell(0,5,"- "+remover_acentos(x),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            else:
                pdf.set_font("Helvetica","",9)
                if content and title=="SINAIS DE DECISÃO":
                    for s in content[:10]:
                        pdf.set_font("Helvetica","B",10); pdf.multi_cell(0,5,remover_acentos(f"{s.get('tipo')} | {s.get('impacto')} | {s.get('urgencia')} | {s.get('titulo')}"),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
                        pdf.set_font("Helvetica","",9); pdf.multi_cell(0,5,remover_acentos("Racional: "+str(s.get('racional',''))),new_x=XPos.LMARGIN,new_y=YPos.NEXT); pdf.multi_cell(0,5,remover_acentos("Acao: "+str(s.get('acao',''))),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
                        pdf.set_font("Helvetica","I",8); pdf.multi_cell(0,4,remover_acentos("Evidencia: "+ref_text(s.get('evidence_ids',[]))),new_x=XPos.LMARGIN,new_y=YPos.NEXT); pdf.ln(2); pdf.set_font("Helvetica","",9)
                elif title=="RADAR DE EVENTOS":
                    for e in content: pdf.multi_cell(0,4.5,remover_acentos(f"{e['kind']} | {e['importance']}/100 | conf. {int(float(e.get('confidence',0))*100)}% | {e.get('date') or 'sem data'} | {e['title']} | {ref_text(e.get('evidence_ids',[]))}"),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
                else:
                    for x in (content or []): pdf.multi_cell(0,5,"- "+remover_acentos(x),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
        pdf.add_page(); pdf.set_text_color(19,67,110); pdf.set_font("Helvetica","B",14); pdf.cell(0,8,"ANEXO - EVIDENCIAS AUDITAVEIS",new_x=XPos.LMARGIN,new_y=YPos.NEXT); pdf.set_text_color(25,35,45)
        for f in fontes:
            pdf.set_font("Helvetica","B",8); pdf.multi_cell(0,4.5,remover_acentos(f"[FONTE {f.id}] {f.titulo}"),new_x=XPos.LMARGIN,new_y=YPos.NEXT)
            pdf.set_font("Helvetica","",7); pdf.multi_cell(0,4,remover_acentos(f"{f.url} | Data: {f.data_publicacao or 'nao identificada'} | Escopo: {f.escopo} | Confianca: {f.confianca:.2f}"),new_x=XPos.LMARGIN,new_y=YPos.NEXT); pdf.ln(1)
        caminho=PASTA_EXECUCAO/f"Sniper_{re.sub(r'[^A-Za-z0-9_-]+','_',EMPRESA_ALVO)}_{RUN_ID}.pdf"; pdf.output(str(caminho)); return str(caminho.resolve())
    except Exception as e:
        logger.error("[PDF] %s",str(e)[:200]); return None

# ============================================================
# 14. EXPORTAÇÃO
# ============================================================

def salvar_json(nome: str, obj: Any) -> str:
    path = PASTA_EXECUCAO / nome
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(path.resolve())


def salvar_csv_fontes(fontes: List[Fonte]) -> str:
    path = PASTA_EXECUCAO / "fontes.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ID", "Categoria", "Titulo", "URL", "Data", "Origem", "Escopo", "Atual", "Score", "Confianca"])
        for x in fontes:
            w.writerow([x.id, x.categoria, x.titulo, x.url, x.data_publicacao, x.origem, x.escopo, x.atual, round(x.score, 1), round(x.confianca, 3)])
    return str(path.resolve())

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

    tavily_client = inicializar_tavily()
    brutas = coletar_tudo(tavily_client)
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

    fontes = enriquecer(fontes)
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
    comparacao_precos = comparar_precos(fontes, memoria, raw_results=brutas, tavily_client=tavily_client)
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

    logger.info("=" * 90)
    logger.info("EXECUÇÃO CONCLUÍDA em %.1fs", time.time() - inicio)
    logger.info("Dashboard: %s", html_path.resolve())
    logger.info("PDF: %s", pdf_path or "não gerado")
    pressao_txt = ambiente.get("pressao_competitiva", {}).get("score")
    cp = comparacao_precos
    logger.info("Preços: %s | comparáveis=%s | alvo_mais_barato=%s | concorrente_mais_barato=%s | snapshots=%s | mudanças=%s", cp.get("status"), cp.get("comparaveis", 0), cp.get("alvo_mais_barato", 0), cp.get("concorrente_mais_barato", 0), cp.get("snapshots_observados", 0), len(cp.get("historico", {}).get("mudancas", [])))
    logger.info("Fontes: %d | Eventos: %d | Atividade empresa: %d/100 | Pressão competitiva: %s | Momentum: %d/100 | Vulnerabilidade: %d/100", len(fontes), len(events), ambiente["score"], pressao_txt if pressao_txt is not None else "N/C", ambiente["momentum_mercado"], ambiente["vulnerabilidade_empresa"]["score"])
    logger.info("=" * 90)

if __name__ == "__main__":
    main()
