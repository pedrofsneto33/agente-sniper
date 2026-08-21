"""
Módulo de Monitoramento, Extração e Comparação de Preços (Pricing Service).
Parte da Fase 42B do Agente Sniper.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from html import unescape as html_unescape
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from domain.models import Fonte, PriceItem
from domain.normalizer import normalizar, parse_money
from domain.identity import dominio, sha1, url_normalizada
from domain.matching import similaridade_produto
from domain.pricing import detectar_mudancas_preco, calcular_serie_temporal_precos
from domain.profiles import obter_perfil_nicho
from web.browser import PersistentPlaywrightManager

logger = logging.getLogger("agente_sniper.pricing")

# Configurações canônicas de ambiente
HOJE = datetime.now()
RUN_ID = HOJE.strftime("%Y%m%d_%H%M%S")

EMPRESA_ALVO = os.getenv("EMPRESA_ALVO", "Supermercado Carvalho").strip()
NICHO = os.getenv("NICHO", "supermercado").strip()
CIDADE = os.getenv("CIDADE", "Teresina").strip()
ESTADO = os.getenv("ESTADO", "PI").strip()
CONCORRENTES = [x.strip() for x in os.getenv("CONCORRENTES", "").split("|") if x.strip()]

PRECO_ALVO_URLS = [x.strip() for x in os.getenv("PRECO_ALVO_URLS", "").split("|") if x.strip()]
PRECO_SOURCES_JSON = os.getenv("PRICE_SOURCES_JSON", "").strip()

MONITORAR_PRECOS = os.getenv("MONITORAR_PRECOS", "1") == "1"
PRECO_USAR_PLAYWRIGHT = os.getenv("PRECO_USAR_PLAYWRIGHT", "0") == "1"
PLAYWRIGHT_ATIVO = os.getenv("PLAYWRIGHT_ATIVO", "0") == "1"
PRICE_REQUIRE_COMMERCIAL_SIGNAL = os.getenv("PRICE_REQUIRE_COMMERCIAL_SIGNAL", "1") == "1"
PRICE_SITE_DISCOVERY = os.getenv("PRICE_SITE_DISCOVERY", "1") == "1"

PRICE_PLAYWRIGHT_TIMEOUT = min(int(os.getenv("PRICE_PLAYWRIGHT_TIMEOUT", "10000")), 10000)
PRICE_MAX_HTTP_FETCHES = min(int(os.getenv("PRICE_MAX_HTTP_FETCHES", "30")), 30)
PRICE_CRAWL_LINK_LIMIT = int(os.getenv("PRICE_CRAWL_LINK_LIMIT", "8"))
PRICE_DISCOVERY_LIMIT_PER_ENTITY = int(os.getenv("PRICE_DISCOVERY_LIMIT_PER_ENTITY", "4"))
PRICE_MAX_DOMAINS_PER_ENTITY = int(os.getenv("PRICE_MAX_DOMAINS_PER_ENTITY", "2"))
MAX_PRECO_ITENS = int(os.getenv("MAX_PRECO_ITENS", "15"))
MAX_BUSCAS_PRECO_CONCORRENTE = int(os.getenv("MAX_BUSCAS_PRECO_CONCORRENTE", "10"))
PRECO_MAX_RESULTADOS_POR_BUSCA = int(os.getenv("PRECO_MAX_RESULTADOS_POR_BUSCA", "6"))
PRECO_MIN_SIMILARIDADE = float(os.getenv("PRECO_MIN_SIMILARIDADE", "0.62"))
PRECO_MAX_OCR_ITENS_POR_PAGINA = int(os.getenv("PRECO_MAX_OCR_ITENS_POR_PAGINA", "80"))
EXTRACTION_ENGINE = os.getenv("EXTRACTION_ENGINE", "legacy").strip().lower()

REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "15.0"))
SITEMAP_PROBING_TIMEOUT = float(os.getenv("SITEMAP_PROBING_TIMEOUT", "4.0"))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

MONEY_RE = re.compile(r"R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?|[0-9]+(?:\.[0-9]{2}))", re.I)

PRICE_DISCOVERY_PATH_HINTS = [
    x.strip().lower() for x in os.getenv(
        "PRICE_DISCOVERY_PATH_HINTS",
        "ofertas|promocao|encarte|tabloide|catalogo|produtos|mercado|comprar|supermercado|loja|loja-online|precos|folheto"
    ).split("|") if x.strip()
]

PRICE_BLOCKED_DOMAINS = {
    x.strip().lower() for x in os.getenv(
        "PRICE_BLOCKED_DOMAINS",
        "jusbrasil.com.br|reclameaqui.com.br|procon|gov.br|facebook.com|instagram.com|linkedin.com|tiktok.com|youtube.com|twitter.com|x.com|g1.globo.com|folha.uol.com.br|estadao.com.br|infomoney.com.br|valor.globo.com|glassdoor.com.br|indeed.com|catho.com.br|infojobs.com.br|vagas.com.br|trabalhabrasil.com.br"
    ).split("|") if x.strip()
}

PRICE_NONCOMMERCIAL_URL_HINTS = [
    x.strip().lower() for x in os.getenv(
        "PRICE_NONCOMMERCIAL_URL_HINTS",
        "noticia|noticias|materia|artigo|blog|reportagem|politica|policial|cidade|trabalhe-conosco|vagas|vaga|carreiras|rh|sobre-nos|quem-somos|investidores|imprensa|privacidade|termos|contato|fale-conosco"
    ).split("|") if x.strip()
]
PRICE_NEGATIVE_PATH_HINTS = PRICE_NONCOMMERCIAL_URL_HINTS
PRICE_PAGE_NEGATIVE_TERMS = set(PRICE_NONCOMMERCIAL_URL_HINTS)

PRICE_COMMERCIAL_CONTENT_HINTS = [
    x.strip().lower() for x in os.getenv(
        "PRICE_COMMERCIAL_CONTENT_HINTS",
        "carrinho|adicionar ao carrinho|comprar|por r$|de r$|preco|preço|oferta|desconto|promocao|promoção"
    ).split("|") if x.strip()
]

PRICE_PRODUCT_SCHEMA_TYPES = {
    x.strip().lower() for x in os.getenv(
        "PRICE_COMMERCIAL_SCHEMA_TYPES", "product|service|offer|aggregateoffer"
    ).split("|") if x.strip()
}


def _source_domain_root(url: str) -> str:
    return dominio(url)


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
    if path in {"", "/", "/home", "/index.html", "/index.php"}:
        score += 0.05
    if negative:
        score -= 0.15
    return max(-1.0, min(1.0, score))


def carregar_price_sources(nicho: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Carrega fontes comerciais de preços respeitando estritamente a precedência arquitetural:
    1. PRECO_ALVO_URLS (explícito via .env ou parâmetro)
    2. PRICE_SOURCES_JSON (explícito via .env ou parâmetro)
    3. commercial_sources do perfil de nicho ativo (domain/profiles.py)
    4. Lista vazia [] (permitindo auto-descoberta ou degradação segura)
    """
    empresa_alvo = os.getenv("EMPRESA_ALVO", EMPRESA_ALVO).strip()

    # 1. PRECO_ALVO_URLS (Configuração explícita de URLs do alvo)
    preco_alvo_urls_env = os.getenv("PRECO_ALVO_URLS", "").strip()
    preco_alvo_urls = [x.strip() for x in preco_alvo_urls_env.split("|") if x.strip()] if preco_alvo_urls_env else PRECO_ALVO_URLS
    if preco_alvo_urls:
        return [{"name": empresa_alvo, "role": "target", "url": u} for u in preco_alvo_urls]

    # 2. PRICE_SOURCES_JSON (Configuração explícita de catálogo JSON)
    preco_sources_json = os.getenv("PRICE_SOURCES_JSON", PRECO_SOURCES_JSON).strip()
    if preco_sources_json:
        try:
            obj = json.loads(preco_sources_json)
            if isinstance(obj, list):
                sources = [x for x in obj if isinstance(x, dict) and x.get("name")]
                if sources:
                    return sources
        except Exception:
            pass

    # 3. commercial_sources declaradas no perfil de nicho ativo
    if nicho is None:
        nicho = os.getenv("NICHO", NICHO)
    perfil = obter_perfil_nicho(nicho)
    comm_sources = perfil.get("commercial_sources") or []
    if isinstance(comm_sources, list) and comm_sources:
        return [dict(x) for x in comm_sources if isinstance(x, dict) and x.get("name") and x.get("url")]

    return []


PRICE_SOURCES = carregar_price_sources()

# Gerenciamento de rede e HTTP Pooling
_HTTP_SESSION: Optional[requests.Session] = None
_HTTP_LOCK = threading.Lock()


def get_http_session() -> requests.Session:
    """Retorna ou inicializa uma Session HTTP reutilizável com pooling de conexões e keep-alive."""
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        with _HTTP_LOCK:
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


_PLAYWRIGHT_MGR = PersistentPlaywrightManager(ativo=PLAYWRIGHT_ATIVO)
_PRICE_HTTP_CACHE: Dict[str, Tuple[str, str, float]] = {}
_PRICE_FETCH_COUNT = 0
_DOMAIN_EXPANSION_CACHE: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
_SITEMAP_DEAD_DOMAINS: Set[str] = set()


def _fetch_html_http(url: str, timeout: Optional[float] = None) -> Tuple[str, str]:
    req_timeout = timeout if timeout is not None else REQUEST_TIMEOUT
    try:
        session = get_http_session()
        r = session.get(url, timeout=req_timeout, allow_redirects=True)
        ctype = (r.headers.get("content-type") or "").lower()
        if r.ok and ("html" in ctype or "xml" in ctype) and len(r.text) > 200:
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
    if not url:
        return []
    if _is_blocked_price_domain(url):
        return []
    dom = _source_domain_root(url)
    if not dom:
        return []

    dom_norm = normalizar(dom).strip()
    name_norm = normalizar(name).strip()
    cache_key = (dom_norm, name_norm, role)

    # 1. Deduplicação e Cache Hit na execução atual
    if cache_key in _DOMAIN_EXPANSION_CACHE:
        return [dict(x) for x in _DOMAIN_EXPANSION_CACHE[cache_key]]

    candidates = [url]
    root = f"https://{dom}"
    if root not in candidates:
        candidates.append(root)

    sitemap_urls = []
    if dom_norm in _SITEMAP_DEAD_DOMAINS:
        pass
    else:
        sitemap_urls = [f"https://{dom}/sitemap.xml", f"https://{dom}/sitemap_index.xml"]

    discovered = []
    sitemap_found = False

    # 2. Probing de páginas candidatas
    for seed in candidates:
        html, final = _fetch_html_http(seed, timeout=min(REQUEST_TIMEOUT, 10.0))
        if html:
            discovered.append(final)
            discovered.extend(_extract_commercial_links(final, html, PRICE_CRAWL_LINK_LIMIT))

    # 3. Probing de sitemaps com timeout rápido (4s)
    for seed in sitemap_urls:
        html, final = _fetch_html_http(seed, timeout=SITEMAP_PROBING_TIMEOUT)
        if html and ("<loc>" in html or "<url>" in html or "<sitemap>" in html):
            sitemap_found = True
            for m in re.finditer(r"<loc>(.*?)</loc>", html, flags=re.I | re.S):
                u = html_unescape(m.group(1).strip())
                try:
                    pu = urlparse(u)
                    if pu.netloc == dom or pu.netloc.endswith("." + dom):
                        if is_price_candidate_url(u):
                            discovered.append(u)
                except Exception:
                    continue

    if not sitemap_found and sitemap_urls:
        _SITEMAP_DEAD_DOMAINS.add(dom_norm)

    uniq = []
    seen = set()
    for u in discovered:
        if u in seen or _is_blocked_price_domain(u):
            continue
        seen.add(u)
        uniq.append({"name": name, "role": role, "url": u, "domain": dom, "location_note": location_note, "discovered": True})
    uniq.sort(key=lambda x: _commercial_signal_url(x["url"]), reverse=True)
    res = uniq[:PRICE_DISCOVERY_LIMIT_PER_ENTITY]

    # Armazena no cache da run
    _DOMAIN_EXPANSION_CACHE[cache_key] = [dict(x) for x in res]
    return res


def _discover_official_commercial_urls(fontes: List[Fonte]) -> List[Dict[str, Any]]:
    """Usa URLs já coletadas para inferir domínios comerciais candidatos."""
    candidatos: List[Dict[str, Any]] = []
    seen = set()
    empresa_alvo = os.getenv("EMPRESA_ALVO", EMPRESA_ALVO).strip()
    for f in fontes:
        if not f.entidade or f.entidade == "mercado":
            continue
        dom = _source_domain_root(f.url)
        if not dom or _is_blocked_price_domain(f.url):
            continue
        sig = _commercial_signal_url(f.url)
        if sig <= 0:
            continue
        key = (normalizar(f.entidade), dom)
        if key in seen:
            continue
        seen.add(key)
        role = "target" if normalizar(f.entidade) == normalizar(empresa_alvo) else "competitor"
        candidatos.extend(_expand_commercial_domain(f.url, f.entidade, role,
            "localidade confirmada" if f.cidade_confirmada else "localidade não confirmada"))
    return candidatos


def descobrir_fontes_preco(fontes: List[Fonte], raw_results: Optional[List[Dict[str, Any]]] = None, tavily_client: Any = None) -> List[Dict[str, Any]]:
    if not PRICE_SITE_DISCOVERY:
        return []
    grupos: Dict[str, List[Fonte]] = {}
    auto_candidates: List[Dict[str, Any]] = []
    empresa_alvo = os.getenv("EMPRESA_ALVO", EMPRESA_ALVO).strip()

    # 0) Descoberta direta em resultados brutos já coletados.
    if raw_results:
        seen_raw = set()
        for r in raw_results:
            alvo = str(r.get("alvo") or "").strip()
            if not alvo or alvo == "mercado":
                continue
            url = str(r.get("url") or "").strip()
            dom = _source_domain_root(url)
            if not dom or _is_blocked_price_domain(url):
                continue
            key = (normalizar(alvo), dom)
            if key in seen_raw:
                continue
            title = normalizar(str(r.get("titulo") or ""))
            body = normalizar(str(r.get("conteudo") or ""))
            sig = _commercial_signal_url(url)
            official_hint = any(k in title or k in body for k in [
                "comprar online", "loja online", "loja virtual", "catalogo", "produtos", "ofertas", "precos", "supershop", "ecommerce"
            ])
            if sig <= 0 and not official_hint:
                continue
            role = "target" if normalizar(alvo) == normalizar(empresa_alvo) else "competitor"
            auto_candidates.extend(_expand_commercial_domain(url, alvo, role, "descoberta comercial"))
            seen_raw.add(key)

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
        if _is_non_commercial_url(f.url) or _is_non_commercial_url(f.titulo):
            continue
        grupos.setdefault(f.entidade, [])
        if len(grupos[f.entidade]) < PRICE_DISCOVERY_LIMIT_PER_ENTITY:
            grupos[f.entidade].append(f)
    out = []
    out.extend(auto_candidates)
    out.extend(_discover_official_commercial_urls(fontes))
    for entidade, fs in grupos.items():
        role = "target" if normalizar(entidade) == normalizar(empresa_alvo) else "competitor"
        ordered = sorted(fs, key=lambda x: (1 if is_price_candidate_url(x.url) else 0, x.direta, x.cidade_confirmada, x.atual, x.score), reverse=True)
        seen_domains = set()
        count = 0
        for f in ordered:
            dom = _source_domain_root(f.url)
            if not dom or dom in seen_domains or _is_blocked_price_domain(f.url):
                continue
            if PRICE_REQUIRE_COMMERCIAL_SIGNAL and _commercial_signal_url(f.url) <= 0:
                expanded = _expand_commercial_domain(f.url, entidade, role, "localidade confirmada" if f.cidade_confirmada else "localidade não confirmada")
                for src in expanded:
                    if src["domain"] not in seen_domains:
                        out.append(src)
                        seen_domains.add(src["domain"])
                        count += 1
                    if count >= PRICE_DISCOVERY_LIMIT_PER_ENTITY:
                        break
                continue
            out.append({"name": entidade, "role": role, "url": f.url, "domain": dom, "location_note": "localidade confirmada" if f.cidade_confirmada else "localidade não confirmada", "discovered": True})
            seen_domains.add(dom)
            count += 1
            if count >= PRICE_DISCOVERY_LIMIT_PER_ENTITY:
                break
    expanded_out = []
    for src in out:
        expanded_out.append(src)
    entities = {src["name"] for src in out}
    for entity in entities:
        base = [src for src in out if src["name"] == entity][:PRICE_MAX_DOMAINS_PER_ENTITY]
        for src in base:
            expanded_out.extend(_expand_commercial_domain(src["url"], entity, src["role"], src.get("location_note", "")))
    uniq = []
    seen = set()
    for src in expanded_out:
        k = (normalizar(src.get("name", "")), src.get("domain") or _source_domain_root(src.get("url", "")), src.get("role", ""), src.get("url", ""))
        if not src.get("url") or k in seen:
            continue
        seen.add(k)
        uniq.append(src)
    return uniq


def mesclar_price_sources(
    fontes: List[Fonte],
    raw_results: Optional[List[Dict[str, Any]]] = None,
    tavily_client: Any = None,
    nicho: Optional[str] = None
) -> List[Dict[str, Any]]:
    merged = []
    seen = set()
    price_sources = carregar_price_sources(nicho=nicho)
    for src in list(price_sources) + descobrir_fontes_preco(fontes, raw_results=raw_results, tavily_client=tavily_client):
        name = str(src.get("name") or "").strip()
        url = str(src.get("url") or "").strip()
        if not name or not url:
            continue
        key = (normalizar(name), _source_domain_root(url), str(src.get("role", "competitor")))
        if key in seen:
            continue
        seen.add(key)
        merged.append(src)
    return merged


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
    vals = obj.get("@type") or obj.get("type")
    if isinstance(vals, str):
        return {normalizar(vals)}
    if isinstance(vals, list):
        return {normalizar(v) for v in vals if isinstance(v, str)}
    return set()


def _plausible_price(name: str, price: Optional[float], context: str = "") -> bool:
    if price is None or price <= 0 or price > 1_000_000:
        return False
    n = normalizar(name + " " + context)
    bad = ["pib", "receita", "lucro", "investimento", "caixa", "milhoes", "milhões", "bilhoes", "bilhões", "cotacao", "cotação", "dividend", "acoes", "ações", "salario", "salário", "vaga", "emprego", "patrimonio", "patrimônio"]
    return not any(x in n for x in bad)


def _price_item_confidence(obj: Dict[str, Any], page_type: str, name: str, price: Optional[float]) -> float:
    if not name or price is None or price <= 0:
        return 0.0
    types = _schema_types(obj)
    score = 0.40
    if types & PRICE_PRODUCT_SCHEMA_TYPES:
        score += 0.35
    if any(obj.get(k) for k in ["sku", "productId", "gtin", "gtin13", "mpn"]):
        score += 0.10
    if page_type in {"COMMERCIAL_CANDIDATE", "ROOT_CANDIDATE"}:
        score += 0.10
    if obj.get("brand"):
        score += 0.05
    return min(score, 1.0)


def _extract_product_objects(html: str, source: str, role: str, page_url: str, location_note: str = "") -> List[PriceItem]:
    soup = BeautifulSoup(html or "", "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    body = soup.get_text(" ", strip=True)[:7000]
    page_type = _price_page_type(page_url, title, body)
    if page_type in {"BLOCKED", "ARTICLE_OR_EMPLOYMENT"}:
        return []
    found = {}
    for s in soup.find_all("script"):
        raw = s.string or s.get_text(" ", strip=True)
        if not raw or len(raw) < 20:
            continue
        objs = []
        if s.get("type") == "application/ld+json":
            try:
                objs = list(_walk_json(json.loads(raw), 12000))
            except Exception:
                objs = []
        elif page_type == "COMMERCIAL_CANDIDATE":
            for m in re.finditer(r"\{.{0,5000}?(?:price|salePrice|sellingPrice).{0,5000}?\}", raw, flags=re.I | re.S):
                try:
                    objs.append(json.loads(m.group(0)))
                except Exception:
                    pass
        for obj in objs:
            types = _schema_types(obj)
            if types and not (types & PRICE_PRODUCT_SCHEMA_TYPES) and not ("offers" in obj and obj.get("name")):
                continue
            name = str(obj.get("name") or obj.get("productName") or obj.get("title") or "").strip()
            price = _extract_price_from_obj(obj)
            if not name or not _plausible_price(name, price, str(obj.get("description") or "")):
                continue
            conf = _price_item_confidence(obj, page_type, name, price)
            if conf < 0.70:
                continue
            brand = obj.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name", "")
            old_price = None
            for k2 in ["oldPrice", "listPrice", "compareAtPrice", "originalPrice"]:
                if k2 in obj:
                    old_price = parse_money(obj.get(k2))
                    if old_price:
                        break
            unit = str(obj.get("unit") or obj.get("size") or obj.get("quantity") or "").strip()
            sku = str(obj.get("sku") or obj.get("productId") or obj.get("gtin") or obj.get("gtin13") or obj.get("mpn") or "").strip()
            key = normalizar(f"{name} {brand or ''} {unit} {sku}")
            item = PriceItem(source, role, name, page_url, price, old_price, bool(old_price and old_price > price), str(brand or ""), unit, sku, location_note=location_note, evidence_url=page_url)
            item.page_type = page_type
            item.price_confidence = conf
            found.setdefault(key, item)
    if page_type in {"COMMERCIAL_CANDIDATE", "ROOT_CANDIDATE"}:
        for node in soup.find_all(string=MONEY_RE):
            parent = node.parent
            if not parent:
                continue
            container = parent
            for _ in range(2):
                if getattr(container, "parent", None):
                    container = container.parent
            context = container.get_text(" ", strip=True)
            prices = [parse_money(m.group(1)) for m in MONEY_RE.finditer(context)]
            if not prices:
                continue
            price = prices[-1]
            links = [a.get_text(" ", strip=True) for a in container.find_all("a") if a.get_text(" ", strip=True)]
            candidate = " ".join(links[:3]).strip()
            if len(candidate) < 5:
                candidate = re.sub(r"R\$\s*[0-9.,]+", " ", context)
            candidate = re.sub(r"\s+", " ", candidate).strip()
            if not (5 <= len(candidate) <= 180) or not _plausible_price(candidate, price, context):
                continue
            if not any(k in normalizar(context) for k in ["comprar", "carrinho", "produto", "oferta", "promocao", "promoção", "preco", "preço", "servico", "serviço", "cardapio", "reservar"]):
                continue
            key = normalizar(candidate)
            item = PriceItem(source, role, candidate, page_url, price, None, False, "", "", "", location_note=location_note, evidence_url=page_url)
            item.page_type = page_type
            item.price_confidence = 0.78
            found.setdefault(key, item)
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
        session = get_http_session()
        r = session.get(key, timeout=min(REQUEST_TIMEOUT, 12), allow_redirects=True)
        if r.ok and "html" in (r.headers.get("content-type") or "").lower() and len(r.text) > 1000:
            _PRICE_HTTP_CACHE[key] = (r.text, r.url, time.time())
            return r.text, r.url
    except Exception as e:
        logger.debug("[PREÇO HTTP] %s", str(e)[:120])
    # Playwright somente em URL fortemente candidata a comercial/dinâmica.
    if not (use_playwright and PRECO_USAR_PLAYWRIGHT):
        return "", key
    if _commercial_signal_url(key) < 0.55 or _is_non_commercial_url(key):
        return "", key
    html, final_url = _PLAYWRIGHT_MGR.extrair_html_preco(key, timeout=PRICE_PLAYWRIGHT_TIMEOUT)
    if html:
        _PRICE_HTTP_CACHE[key] = (html, final_url, time.time())
        return html, final_url
    return "", key


def _buscar_preco_site(url_template: str, query: str) -> str:
    return url_template.format(query=quote_plus(query), q=quote_plus(query), termo=quote_plus(query))


def coletar_itens_preco_fonte(source: Dict[str, Any], query: str = "") -> List[PriceItem]:
    url = source.get("url", "")
    role = source.get("role", "competitor")
    name = source.get("name", "Fonte")
    location_note = str(source.get("location_note", ""))
    channel_type = str(source.get("channel_type", "html_catalog")).strip().lower()

    engine = os.getenv("EXTRACTION_ENGINE", EXTRACTION_ENGINE).strip().lower()
    if engine not in {"legacy", "generic", "shadow"}:
        engine = "legacy"

    # Se a fonte contiver arquivo ou payload de OCR bruto (folhetos, tablóides, encartes)
    ocr_origem = source.get("ocr_path") or source.get("ocr_json") or source.get("deteccoes")

    # Fontes do tipo flyer_ocr sem payload OCR local: degradação segura e explícita
    if channel_type == "flyer_ocr" and not ocr_origem:
        logger.info("[PREÇOS] canal 'flyer_ocr' sem payload OCR local: %s (%s)", name, url)
        return []

    # Fontes do tipo interactive_catalog sem adaptador interativo: degradação segura e explícita
    if channel_type == "interactive_catalog" and not source.get("search_url"):
        logger.info("[PREÇOS] canal 'interactive_catalog' sem adaptador interativo: %s (%s)", name, url)
        return []
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
    if not PRECO_USAR_PLAYWRIGHT:
        return {}
    cidade = os.getenv("CIDADE", CIDADE).strip()
    return _PLAYWRIGHT_MGR.session_search(
        base_url,
        search_url_template,
        queries,
        location_hint=location_hint,
        buscar_preco_fn=_buscar_preco_site,
        extract_products_fn=_extract_product_objects,
        cidade=cidade,
        normalizar_fn=normalizar,
        max_results=PRECO_MAX_RESULTADOS_POR_BUSCA,
    )


def comparar_precos(
    fontes: List[Fonte],
    memoria: Optional[Any] = None,
    raw_results: Optional[List[Dict[str, Any]]] = None,
    tavily_client: Any = None,
    nicho: Optional[str] = None
) -> Dict[str, Any]:
    monitorar = os.getenv("MONITORAR_PRECOS", "1") == "1"
    if not monitorar:
        return {"enabled": False, "reason": "monitoramento desativado"}
    series_temporais = {}
    if memoria:
        try:
            raw_series = memoria.get_price_series(hoje=HOJE)
            for (ent, s_dom, p_key), s_data in raw_series.items():
                d = dict(s_data)
                d["entity"] = ent
                d["source_domain"] = s_dom
                d["product_key"] = p_key
                series_temporais[f"{ent}::{s_dom}::{p_key}"] = d
        except Exception as e:
            logger.warning("[PRICE SERIES] Falha ao recuperar séries de preços: %s", str(e)[:100])
    sources = mesclar_price_sources(fontes, raw_results=raw_results, tavily_client=tavily_client, nicho=nicho)
    logger.info("[PREÇOS] fontes candidatas=%d | budget_fetches=%d", len(sources), PRICE_MAX_HTTP_FETCHES)
    for _src in sources[:12]:
        logger.info("[PREÇOS] candidato %s | %s | %s", _src.get("role"), _src.get("name"), _src.get("url"))
    targets = [x for x in sources if x.get("role") == "target"]
    competitors = [x for x in sources if x.get("role") == "competitor"]
    if not targets:
        logger.warning("[PREÇOS] nenhuma fonte comercial do alvo foi descoberta. Configure PRECO_ALVO_URLS/PRICE_SOURCES_JSON ou verifique buscas comerciais.")
        return {"enabled": True, "status": "sem_fonte_de_preco_do_alvo", "comparacoes": [], "fontes_descobertas": sources, "series_temporais": series_temporais}
    if not competitors:
        return {"enabled": True, "status": "sem_fontes_de_concorrentes", "comparacoes": [], "fontes_descobertas": sources, "series_temporais": series_temporais}
    item_cache: Dict[str, List[PriceItem]] = {}

    def cached_items(src: Dict[str, Any]) -> List[PriceItem]:
        key = f"{src.get('role','')}|{src.get('name','')}|{src.get('domain','')}|{src.get('url','')}"
        if key not in item_cache:
            item_cache[key] = coletar_itens_preco_fonte(src)
        return item_cache[key]

    # Deduplica por entidade/domínio e limita fontes para evitar crawler explosivo.
    concorrentes_env = [x.strip() for x in os.getenv("CONCORRENTES", "").split("|") if x.strip()] if os.getenv("CONCORRENTES") else CONCORRENTES

    def compact_sources(arr: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        seen = set()
        for x in sorted(arr, key=lambda s: _commercial_signal_url(s.get('url', '')), reverse=True):
            k = (normalizar(x.get('name', '')), _source_domain_root(x.get('url', '')), x.get('role', ''))
            if not k[1] or k in seen:
                continue
            seen.add(k)
            out.append(x)
            if len([y for y in out if y.get('role') == x.get('role')]) >= PRICE_MAX_DOMAINS_PER_ENTITY * max(1, len(concorrentes_env) + 1):
                break
        return out

    targets = compact_sources(targets)[:PRICE_MAX_DOMAINS_PER_ENTITY]
    competitors = compact_sources(competitors)
    target_items = []
    for src in targets:
        target_items.extend(cached_items(src))
    uniq = {}
    for it in target_items:
        if it.key():
            uniq.setdefault(it.key(), it)
    target_items = [x for x in uniq.values() if getattr(x, "price_confidence", 0.0) >= 0.70]
    target_items = list(target_items)[:MAX_PRECO_ITENS]
    if not target_items:
        return {"enabled": True, "status": "sem_produtos_alvo", "comparacoes": [], "produtos_alvo": 0, "fontes_descobertas": sources, "series_temporais": series_temporais}
    comparacoes = []
    for comp in competitors:
        catalog = cached_items(comp)
        search_template = str(comp.get("search_url", "")).strip()
        session_results = {}
        queries = [" ".join(x for x in [t.brand, t.name, t.unit] if x).strip() for t in target_items[:MAX_BUSCAS_PRECO_CONCORRENTE]] if search_template else []
        if search_template and PRECO_USAR_PLAYWRIGHT:
            session_results = _playwright_session_search(str(comp.get("url", "")), search_template, queries, str(comp.get("location_note", "")))
        for target in target_items[:MAX_BUSCAS_PRECO_CONCORRENTE]:
            q = " ".join(x for x in [target.brand, target.name, target.unit] if x).strip()
            results = list(catalog)
            if session_results.get(q):
                results.extend(session_results[q])
            if not results and search_template:
                results = coletar_itens_preco_fonte(comp, q)
            if not results:
                comparacoes.append({"produto_alvo": target.name, "marca": target.brand, "unidade": target.unit, "alvo_preco": target.price, "alvo_promocao": target.promotion, "concorrente": comp.get("name", ""), "concorrente_produto": "", "concorrente_preco": None, "similaridade": 0.0, "dif_percent": None, "mais_barato": "não encontrado", "confianca_match": "baixa", "url_alvo": target.url, "url_concorrente": comp.get("url", ""), "location_note": comp.get("location_note", "")})
                continue
            results = [r for r in results if getattr(r, "price_confidence", 0.0) >= 0.70 and _price_page_type(r.url, getattr(r, "page_type", ""), r.name) not in {"BLOCKED", "ARTICLE_OR_EMPLOYMENT"}]
            if not results:
                comparacoes.append({"produto_alvo": target.name, "marca": target.brand, "unidade": target.unit, "alvo_preco": target.price, "alvo_promocao": target.promotion, "concorrente": comp.get("name", ""), "concorrente_produto": "", "concorrente_preco": None, "similaridade": 0.0, "match_class": "nao_encontrado", "dif_percent": None, "mais_barato": "não encontrado", "confianca_match": "baixa", "url_alvo": target.url, "url_concorrente": comp.get("url", ""), "location_note": comp.get("location_note", "")})
                continue
            ranked = sorted(((similaridade_produto(target, r), r) for r in results), key=lambda x: x[0], reverse=True)
            sim, best = ranked[0]
            row = {"produto_alvo": target.name, "marca": target.brand, "unidade": target.unit, "alvo_preco": target.price, "alvo_old_price": target.old_price, "alvo_promocao": target.promotion, "concorrente": comp.get("name", ""), "concorrente_produto": best.name, "concorrente_preco": best.price, "concorrente_old_price": best.old_price, "concorrente_promocao": best.promotion, "similaridade": round(sim, 3), "url_alvo": target.url, "url_concorrente": best.url, "location_note": best.location_note or comp.get("location_note", ""), "canonical_product_id": sha1(normalizar(f"{target.brand}|{target.name}|{target.unit}|{target.sku}"))[:24]}
            if sim >= PRECO_MIN_SIMILARIDADE and target.price and best.price:
                row["dif_percent"] = round((best.price - target.price) / target.price * 100, 2)
                if abs(row["dif_percent"]) > 300:
                    row["dif_percent"] = None
                    row["mais_barato"] = "não comparável"
                    row["match_class"] = "revisao_necessaria"
                    row["confianca_match"] = "baixa"
                else:
                    row["mais_barato"] = "concorrente" if best.price < target.price else "alvo" if target.price < best.price else "igual"
                    row["match_class"] = "confirmado" if sim >= 0.90 else "provavel"
                    row["confianca_match"] = "alta" if sim >= 0.88 else "media"
            else:
                row["dif_percent"] = None
                row["mais_barato"] = "não comparável"
                row["match_class"] = "nao_comparavel"
                row["confianca_match"] = "baixa"
            comparacoes.append(row)
    snapshots = []
    for src in targets + competitors:
        entity = str(src.get("name") or "")
        role = str(src.get("role") or "")
        items = cached_items(src)
        for it in items:
            snapshots.append({"entity": entity, "role": role, "source_domain": dominio(it.url or src.get("url", "")), "product_key": it.key(), "product_name": it.name, "brand": it.brand, "unit": it.unit, "price": it.price, "old_price": it.old_price, "promotion": it.promotion, "url": it.url, "location_note": it.location_note})
    history = memoria.save_price_snapshots(RUN_ID, snapshots) if memoria else {"previous_run": None, "gravados": 0, "mudancas": []}
    comparable = [x for x in comparacoes if x.get("dif_percent") is not None]
    by_comp = {}
    for row in comparable:
        by_comp.setdefault(row["concorrente"], []).append(row)
    guerra = []
    for comp, rows in by_comp.items():
        ds = [r["dif_percent"] for r in rows]
        guerra.append({"concorrente": comp, "comparaveis": len(rows), "concorrente_mais_barato": sum(r["mais_barato"] == "concorrente" for r in rows), "alvo_mais_barato": sum(r["mais_barato"] == "alvo" for r in rows), "empates": sum(r["mais_barato"] == "igual" for r in rows), "dif_media_percent": round(sum(ds) / len(ds), 2), "dif_mediana_percent": round(sorted(ds)[len(ds) // 2], 2), "maior_gap_percent": round(max(ds, key=lambda z: abs(z)), 2)})
    guerra.sort(key=lambda x: (x["concorrente_mais_barato"], abs(x["dif_media_percent"])), reverse=True)
    return {"enabled": True, "status": "ok" if comparable else "sem_matches_confiaveis", "produtos_alvo": len(target_items), "comparacoes": comparacoes, "comparaveis": len(comparable), "alvo_mais_barato": sum(x["mais_barato"] == "alvo" for x in comparable), "concorrente_mais_barato": sum(x["mais_barato"] == "concorrente" for x in comparable), "promocoes_alvo": sum(bool(x.get("alvo_promocao")) for x in comparacoes), "promocoes_concorrentes": sum(bool(x.get("concorrente_promocao")) for x in comparacoes), "maiores_gaps": sorted(comparable, key=lambda x: abs(x.get("dif_percent", 0)), reverse=True)[:15], "fontes": sources, "guerra_de_precos": guerra, "historico": history, "series_temporais": series_temporais, "snapshots_observados": len(snapshots), "metodologia": "descoberta automática de domínios comerciais + expansão de homepage/sitemap/links comerciais; catálogo direto e pesquisa por produto quando disponível; matching por nome/marca/unidade; somente matches acima do limiar entram na comparação; snapshots persistidos em SQLite para histórico de guerra de preços."}


__all__ = [
    "MONEY_RE",
    "PRICE_SOURCES",
    "PRICE_PRODUCT_SCHEMA_TYPES",
    "PRICE_BLOCKED_DOMAINS",
    "PRICE_NONCOMMERCIAL_URL_HINTS",
    "PRICE_NEGATIVE_PATH_HINTS",
    "PRICE_PAGE_NEGATIVE_TERMS",
    "PRICE_COMMERCIAL_CONTENT_HINTS",
    "PRICE_DISCOVERY_PATH_HINTS",
    "get_http_session",
    "_is_non_commercial_url",
    "_price_page_type",
    "_is_blocked_price_domain",
    "is_price_candidate_url",
    "_commercial_signal_url",
    "carregar_price_sources",
    "_fetch_html_http",
    "_extract_commercial_links",
    "_expand_commercial_domain",
    "_discover_official_commercial_urls",
    "descobrir_fontes_preco",
    "mesclar_price_sources",
    "_walk_json",
    "_extract_price_from_obj",
    "_schema_types",
    "_plausible_price",
    "_price_item_confidence",
    "_extract_product_objects",
    "_price_page_html",
    "_buscar_preco_site",
    "coletar_itens_preco_fonte",
    "_playwright_session_search",
    "comparar_precos",
]
