"""
Módulo de Normalização, Scoring e Validação de Fontes (Domain Layer).
Parte da Fase 40 do Agente Sniper.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from domain.identity import (
    cidade_ok as _identity_cidade_ok,
    data_publicacao,
    dominio,
    estado_ok as _identity_estado_ok,
    identidade_conflitante as _identity_identidade_conflitante,
    sha1,
    url_normalizada,
)
from domain.models import Fonte
from domain.normalizer import normalizar, termo

logger = logging.getLogger("agente_sniper.sources")

HOJE = datetime.now(timezone.utc)

DOMINIOS_PRIORITARIOS: Dict[str, float] = {
    "gov.br": 1.00,
    "reclameaqui.com.br": 0.95,
    "procon": 0.95,
    "g1.globo.com": 0.92,
}

CIDADES_EXTERIORES: Set[str] = {
    "jundiai", "cubatao", "redmond", "washington", "new york", "california", "florida",
    "texas", "miami", "los angeles", "london", "madrid", "lisboa", "paris",
}


def _source_domain_root(url: str) -> str:
    return dominio(url)


def _get_empresa_alvo() -> str:
    return os.getenv("EMPRESA_ALVO", "Supermercado Carvalho").strip()


def _get_cidade() -> str:
    return os.getenv("CIDADE", "Teresina").strip()


def _get_estado() -> str:
    return os.getenv("ESTADO", "PI").strip()


def _get_ano_minimo_historico() -> int:
    return int(os.getenv("ANO_MINIMO_HISTORICO", "2020"))


def _get_ano_minimo_atual() -> int:
    return int(os.getenv("ANO_MINIMO_ATUAL", str(max(2025, HOJE.year - 1))))


def _get_termos_conflitantes() -> Optional[List[str]]:
    env = os.getenv("TERMOS_CONFLITANTES_IDENTIDADE", "").strip()
    if env:
        return [x.strip() for x in env.split(",") if x.strip()]
    return None


def _get_empresa_aliases() -> List[str]:
    aliases_env = os.getenv("EMPRESA_ALIASES", "").strip()
    if aliases_env:
        return [x.strip() for x in aliases_env.split("|") if x.strip()]
    emp = _get_empresa_alvo()
    return [emp]


def _alias_empresa(texto: str) -> Optional[str]:
    """Identidade conservadora; sobrenome isolado não é alias automático."""
    empresa_alvo = _get_empresa_alvo()
    aliases = _get_empresa_aliases()
    candidatos = [x.strip() for x in aliases if x.strip()]
    partes = [x for x in re.split(r"\s+", normalizar(empresa_alvo)) if len(x) >= 4]
    if len(partes) >= 2:
        candidatos.append(" ".join(partes))
    for a in sorted(set(candidatos), key=len, reverse=True):
        if termo(texto, a):
            return a
    return None


def dominios_oficiais_configurados() -> Set[str]:
    """Deriva dinamicamente os domínios oficiais da empresa-alvo e concorrentes configurados."""
    doms = set()
    emp_url = os.getenv("EMPRESA_URL", "").strip()
    if emp_url:
        r = _source_domain_root(emp_url)
        if r:
            doms.add(r)
    preco_alvo_urls_env = os.getenv("PRECO_ALVO_URLS", "").strip()
    if preco_alvo_urls_env:
        for u in [x.strip() for x in preco_alvo_urls_env.split("|") if x.strip()]:
            r = _source_domain_root(u)
            if r:
                doms.add(r)
    preco_sources_json = os.getenv("PRICE_SOURCES_JSON", "").strip()
    if preco_sources_json:
        try:
            for item in json.loads(preco_sources_json):
                u = item.get("url") or item.get("search_url") or ""
                r = _source_domain_root(u)
                if r:
                    doms.add(r)
        except Exception:
            pass
    return doms


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
    d_root = _source_domain_root(f.url) or d

    # 1. Bônus para domínio oficial da entidade configurada (dinâmico e multinicho)
    doms_oficiais = dominios_oficiais_configurados()
    if d in doms_oficiais or d_root in doms_oficiais:
        s += 8 * 0.85
    else:
        # 2. Domínios de autoridade institucional / regulação / jornalismo geral
        for dom, peso in DOMINIOS_PRIORITARIOS.items():
            if d == dom or dom in d:
                s += 8 * peso
                break
    sinais = f.sinais
    s += min(10, 2 * len(sinais))
    return s


def classificar_escopo(texto: str, corporativo: bool) -> Tuple[str, bool, bool]:
    c, e = _identity_cidade_ok(texto, cidade=_get_cidade()), _identity_estado_ok(texto, estado=_get_estado())
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
    empresa_alvo = _get_empresa_alvo()
    termos_conflitantes = _get_termos_conflitantes()
    if alvo != "mercado" and _identity_identidade_conflitante(texto, empresa_alvo=empresa_alvo, termos_conflitantes=termos_conflitantes):
        return None
    a = _alias_empresa(texto)
    if not a and alvo and alvo != "mercado" and not termo(texto, alvo):
        return None
    if not a and alvo and alvo != "mercado":
        a = alvo
    if not a and alvo != "mercado":
        return None
    corporativo = any(k in dominio(url) for k in [normalizar(x).replace(" ", "") for x in [empresa_alvo, alvo, "grupo", "corporate"] if x])
    escopo, c, e = classificar_escopo(texto, corporativo)
    if alvo == "mercado":
        escopo = "mercado" if not c else "local"
    elif alvo and alvo != empresa_alvo and alvo != "mercado" and termo(texto, alvo):
        # Evidência de concorrente: pode ser nacional/corporativa, mas não deve ser confundida com a empresa-alvo.
        escopo = "concorrente" if not c else "local"
    else:
        # Empresa-alvo: rejeitar fontes geograficamente incompatíveis.
        cidade = _get_cidade()
        if cidade and escopo == "global":
            return None
        if cidade and escopo == "incerto" and not corporativo:
            return None
    data, tipo, d = data_publicacao(raw)
    ano_min_hist = _get_ano_minimo_historico()
    if d and d.year < ano_min_hist:
        return None
    sinais = sinais_deterministicos(texto)
    ano_min_atual = _get_ano_minimo_atual()
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
        atual=bool(d and d.year >= ano_min_atual),
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


__all__ = [
    "DOMINIOS_PRIORITARIOS",
    "CIDADES_EXTERIORES",
    "dominios_oficiais_configurados",
    "score_fonte",
    "classificar_escopo",
    "sinais_deterministicos",
    "transformar",
    "deduplicar",
]
