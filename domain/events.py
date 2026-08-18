# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Detecção, Clustering Canônico e Regras de Eventos de Mercado.
Lógica pura de domínio sem I/O, rede, banco ou apresentação.
"""
import difflib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from domain.models import Fonte
from domain.normalizer import normalizar, truncar, parse_data, score_clamp
from domain.identity import sha1

EVENT_RULES: Dict[str, Dict[str, Any]] = {
    "PREÇO": {"keys": ["preco", "oferta", "promocao", "desconto", "r$"], "base": 60},
    "REPUTAÇÃO": {"keys": ["reclamacao", "reclame", "avaliacao", "nota", "queixa"], "base": 62},
    "ATENDIMENTO": {"keys": ["atendimento", "fila", "demora", "suporte"], "base": 54},
    "EXPANSÃO": {"keys": ["inaugur", "nova unidade", "nova loja", "expansao", "filial"], "base": 74},
    "DIGITAL": {"keys": ["app", "aplicativo", "delivery", "ecommerce", "e-commerce", "plataforma"], "base": 62},
    "MARKETING": {"keys": ["campanha", "evento", "patrocin", "publicidade", "marketing"], "base": 48},
    "PESSOAS": {"keys": ["vaga", "contratacao", "emprego", "recrut"], "base": 44},
    "REGULAÇÃO": {"keys": ["procon", "multa", "fiscalizacao", "anvisa", "sanitaria", "processo"], "base": 78},
    "PRODUTO/SERVIÇO": {"keys": ["lancamento", "produto", "servico", "cardapio", "catalogo"], "base": 52},
    "PARCERIA": {"keys": ["parceria", "acordo", "joint venture", "fornecedor"], "base": 50},
}

RISK_KINDS: Set[str] = {"REPUTAÇÃO", "ATENDIMENTO", "REGULAÇÃO"}
OPPORTUNITY_KINDS: Set[str] = {"PREÇO", "EXPANSÃO", "DIGITAL", "MARKETING", "PRODUTO/SERVIÇO", "PARCERIA"}

EVENT_DATE_CLUSTER_DAYS: int = 45
EVENT_TITLE_SIM_THRESHOLD: float = 0.70
EVENT_TOKEN_SIM_THRESHOLD: float = 0.55
EVENT_CURRENT_WINDOW_DAYS: int = 45
EVENT_CONTEXTUAL_MAX_DAYS: int = 180


def recencia_score(f: Fonte, hoje: Optional[datetime] = None) -> float:
    """Calcula score de recência ponderada da publicação."""
    if not f.data_publicacao:
        return 0.35
    d = parse_data(f.data_publicacao)
    if not d:
        return 0.35
    ref_date = hoje.date() if hoje else datetime.now().date()
    delta = max(0, (ref_date - d.date()).days)
    if delta <= 7: return 1.00
    if delta <= 30: return 0.88
    if delta <= 90: return 0.72
    if delta <= 180: return 0.52
    return 0.30


def qualidade_fonte(f: Fonte) -> float:
    """Calcula índice de confiabilidade e completude da fonte."""
    base = 0.30
    if f.alias_empresa or f.entidade: base += 0.15
    if f.cidade_confirmada: base += 0.15
    elif f.estado_confirmado: base += 0.06
    if f.direta: base += 0.10
    if f.data_publicacao: base += 0.10
    if f.dominio in {"gov.br", "mppi.mp.br", "reclameaqui.com.br", "g1.globo.com"}: base += 0.10
    if f.escopo == "local": base += 0.08
    return min(1.0, base)


def evento_titulo_estavel(f: Fonte, kind: str) -> str:
    """Gera um título limpo e estável para representação canônica do evento."""
    base = re.sub(r"\s+", " ", f.titulo or "").strip()
    generic = {"instagram", "facebook", "youtube", "google notícias", "google noticias", "reclame aqui", "home", "página inicial", "pagina inicial"}
    if normalizar(base) in generic or len(base) < 12:
        base = re.sub(r"\s+", " ", (f.resumo_busca or f.conteudo[:260])).strip()
    base = re.sub(r"\s+[|•-]\s+(Instagram|Facebook|YouTube|Google Notícias|Google Noticias)$", "", base, flags=re.I).strip()
    return truncar(base, 180)


def _evento_tokens(s: str) -> Set[str]:
    """Extrai tokens significativos do evento sem stopwords."""
    stop = {"de", "da", "do", "e", "em", "para", "com", "que", "um", "uma", "na", "no", "por", "a", "o", "os", "as", "dos", "das", "ao", "aos", "sua", "seu", "sobre"}
    return {x for x in re.findall(r"[a-z0-9]{3,}", normalizar(s)) if x not in stop}


def _evento_data(obj: Any) -> Optional[datetime]:
    """Extrai objeto datetime do evento ou fonte."""
    raw = obj.get("date") if isinstance(obj, dict) else getattr(obj, "data_publicacao", "")
    return parse_data(raw) if raw else None


def _same_event_date(a: Dict[str, Any], b: Dict[str, Any], cluster_days: int = EVENT_DATE_CLUSTER_DAYS) -> bool:
    """Verifica se duas ocorrências estão dentro do raio temporal de clustering."""
    da, db = _evento_data(a), _evento_data(b)
    if da and db:
        return abs((da.date() - db.date()).days) <= cluster_days
    return not (a.get("date") or b.get("date"))


def _event_similarity(a_title: str, b_title: str) -> Tuple[float, float]:
    """Calcula similaridade de SequenceMatcher e sobreposição de tokens entre títulos."""
    na, nb = normalizar(a_title), normalizar(b_title)
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = _evento_tokens(na), _evento_tokens(nb)
    tok = len(ta & tb) / max(1, len(ta | tb)) if ta and tb else 0.0
    return seq, tok


def eventos_sao_mesmo_fato(
    a: Dict[str, Any],
    b: Dict[str, Any],
    title_sim_threshold: float = EVENT_TITLE_SIM_THRESHOLD,
    token_sim_threshold: float = EVENT_TOKEN_SIM_THRESHOLD,
    cluster_days: int = EVENT_DATE_CLUSTER_DAYS
) -> bool:
    """Determina se dois eventos representam a mesma ocorrência factual subjacente."""
    if normalizar(a.get("entity")) != normalizar(b.get("entity")) or a.get("kind") != b.get("kind"):
        return False
    if not _same_event_date(a, b, cluster_days=cluster_days):
        return False
    seq, tok = _event_similarity(a.get("title", ""), b.get("title", ""))
    if seq < title_sim_threshold and tok < token_sim_threshold:
        return False
    if a.get("kind") == "REGULAÇÃO":
        keys = {"procon", "multa", "fiscalizacao", "anvisa", "sanitaria", "processo"}
        if not ((_evento_tokens(a.get("title", "")) & keys) and (_evento_tokens(b.get("title", "")) & keys)):
            return False
    return True


def canonical_event_key(f: Fonte, kind: str) -> str:
    """Gera hash SHA-1 canônico de 24 caracteres para agrupamento estável."""
    title = evento_titulo_estavel(f, kind)
    toks = sorted(_evento_tokens(title))
    nums = re.findall(r"\b\d+(?:[.,]\d+)?\b", normalizar(title))
    d = f.data_publicacao[:10] if f.data_publicacao else "sem-data"
    dt = parse_data(d)
    bucket = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d") if dt else "sem-data"
    return sha1(f"{normalizar(f.entidade or f.alias_empresa or 'mercado')}|{kind}|{'local' if f.cidade_confirmada else f.escopo}|{' '.join(toks[:24])}|{','.join(nums[:4])}|{bucket}")[:24]


def _primary_event_kind(f: Fonte, is_price_candidate_fn: Optional[Any] = None) -> Tuple[Optional[str], List[str]]:
    """Identifica a dimensão primária e dimensões correlatas a partir do texto da fonte."""
    n = normalizar(f.texto())
    if any(k in n for k in ["procon", "multa", "fiscalizacao", "anvisa", "vigilancia sanitaria"]):
        return "REGULAÇÃO", ["REGULAÇÃO"]
    if any(k in n for k in ["vaga", "vagas", "emprego", "contratacao", "contratação", "recrutamento", "processo seletivo"]):
        return "PESSOAS", ["PESSOAS"] + (["EXPANSÃO"] if any(k in n for k in ["nova unidade", "nova loja", "inaugur", "filial"]) else [])
    if any(k in n for k in ["inaugur", "nova unidade", "nova loja", "expansao", "expansão", "filial", "abre as portas", "instalação de", "instalacao de", "vai abrir", "planeja abrir"]):
        return "EXPANSÃO", ["EXPANSÃO"]
    if any(k in n for k in ["reclamacao", "reclamação", "reclame aqui", "queixa", "avaliacao", "avaliação", "nota"]):
        return "REPUTAÇÃO", ["REPUTAÇÃO"]
    if any(k in n for k in ["fila", "demora no atendimento", "mau atendimento", "suporte"]):
        return "ATENDIMENTO", ["ATENDIMENTO"]
    if any(k in n for k in ["preco", "preço", "oferta", "promocao", "promoção", "desconto"]):
        if is_price_candidate_fn is None or is_price_candidate_fn(f.url, f.titulo, f.conteudo):
            return "PREÇO", ["PREÇO"]
    if any(k in n for k in ["app", "aplicativo", "delivery", "e-commerce", "ecommerce", "plataforma", "supershop"]):
        return "DIGITAL", ["DIGITAL"]
    if any(k in n for k in ["campanha", "publicidade", "patrocin", "marketing", "evento promocional"]):
        return "MARKETING", ["MARKETING"]
    if any(k in n for k in ["lancamento", "lançamento", "produto novo", "novo produto", "cardapio", "catalogo", "catálogo", "servico", "serviço"]):
        return "PRODUTO/SERVIÇO", ["PRODUTO/SERVIÇO"]
    if any(k in n for k in ["parceria", "acordo", "joint venture", "fornecedor"]):
        return "PARCERIA", ["PARCERIA"]
    return None, []


def criar_eventos(
    fontes: List[Fonte],
    hoje: Optional[datetime] = None,
    current_window_days: int = EVENT_CURRENT_WINDOW_DAYS,
    contextual_max_days: int = EVENT_CONTEXTUAL_MAX_DAYS,
    is_price_candidate_fn: Optional[Any] = None,
    title_sim_threshold: float = EVENT_TITLE_SIM_THRESHOLD,
    token_sim_threshold: float = EVENT_TOKEN_SIM_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Agrupa fontes em eventos canônicos consolidados com corroboração multicanal."""
    ref_now = hoje or datetime.now()
    candidates = []
    for f in fontes:
        kind, dims = _primary_event_kind(f, is_price_candidate_fn=is_price_candidate_fn)
        if not kind:
            continue
        d = _evento_data(f)
        current = bool(d and (ref_now.date() - d.date()).days <= current_window_days)
        contextual = bool(d and (ref_now.date() - d.date()).days <= contextual_max_days)
        eq = qualidade_fonte(f)
        rec = recencia_score(f, hoje=ref_now)
        specificity = 1.0 if f.escopo in {"local", "concorrente"} else 0.82 if f.escopo == "corporativo" else 0.60
        importance = score_clamp(EVENT_RULES[kind]["base"] * (0.55 + 0.25 * eq + 0.15 * rec + 0.05 * specificity))
        if not d:
            importance = score_clamp(importance * 0.68)
        if not current:
            importance = min(importance, 54)
        ev = {
            "event_id": canonical_event_key(f, kind),
            "event_key": canonical_event_key(f, kind),
            "kind": kind,
            "title": evento_titulo_estavel(f, kind),
            "importance": importance,
            "confidence": round(min(1.0, 0.45 * eq + 0.35 * rec + 0.20 * specificity), 2),
            "evidence_ids": [f.id],
            "date": f.data_publicacao or "",
            "scope": f.escopo,
            "entity": f.entidade or f.alias_empresa or "mercado",
            "dimensions": dims,
            "independent_sources": {f.dominio or f.url},
            "source_urls": [f.url],
            "direct": bool(f.direta),
            "current": current,
            "contextual": contextual,
        }
        for ex in candidates:
            if eventos_sao_mesmo_fato(ex, ev, title_sim_threshold=title_sim_threshold, token_sim_threshold=token_sim_threshold):
                ex["evidence_ids"] = sorted(set(ex["evidence_ids"] + [f.id]))
                ex["independent_sources"].add(f.dominio or f.url)
                ex["source_urls"] = sorted(set(ex["source_urls"] + [f.url]))[:12]
                ex["dimensions"] = sorted(set(ex["dimensions"] + dims))
                ex["current"] = ex["current"] or current
                ex["contextual"] = ex["contextual"] or contextual
                ex["direct"] = ex["direct"] or bool(f.direta)
                ex["importance"] = score_clamp(max(ex["importance"], importance) + min(8, 2 * len(ex["independent_sources"])))
                ex["confidence"] = round(min(1.0, max(ex["confidence"], ev["confidence"]) + (0.05 if len(ex["independent_sources"]) >= 2 else 0)), 2)
                if len(ev["title"]) > len(ex["title"]):
                    ex["title"] = ev["title"]
                break
        else:
            candidates.append(ev)
    out = []
    for e in candidates:
        e["independent_source_count"] = len(e.pop("independent_sources"))
        if e["independent_source_count"] >= 2:
            e["confidence"] = round(min(1.0, e["confidence"] + 0.10), 2)
        out.append(e)
    return sorted(out, key=lambda x: (bool(x.get("current")), x["importance"], x["confidence"]), reverse=True)[:60]
