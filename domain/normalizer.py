# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Normalização e Sanitização Textual / Numérica.
Lógica de domínio pura sem I/O, rede, banco ou estado global.
"""
import functools
import re
import unicodedata
from datetime import datetime
from typing import Any, Optional, Tuple, Set

try:
    from dateutil import parser as date_parser
except ImportError:
    date_parser = None

_RE_SPACES = re.compile(r"\s+")
_RE_MONEY_CLEAN = re.compile(r"[^0-9.\-]")
_RE_PROD_UNITS = re.compile(
    r"\b\d+(?:[\.,]\d+)?\s*(?:kg|kilo|quilo|kilos|quilos|g|gr|grama|gramas|mg|miligrama|miligramas|l|lt|litro|litros|ml|mls|mililitro|mililitros|un|und|unidade|unidades|caps|capsula|capsulas|dose|doses|sessoes|sessao|sessões|sessão|diaria|diarias|diária|diárias|noite|noites|peca|peça|pecas|peças|itens|item|m2|m²)\b"
)
_RE_PROD_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_RE_KG = re.compile(r"\b(\d+(?:\.\d+)?)\s*(kg|kilo|quilo|kilos|quilos)\b")
_RE_G = re.compile(r"\b(\d+(?:\.\d+)?)\s*(g|gr|grama|gramas)\b")
_RE_MG = re.compile(r"\b(\d+(?:\.\d+)?)\s*(mg|miligrama|miligramas)\b")
_RE_L = re.compile(r"\b(\d+(?:\.\d+)?)\s*(l|lt|litro|litros)\b")
_RE_ML = re.compile(r"\b(\d+(?:\.\d+)?)\s*(ml|mls|mililitro|mililitros)\b")
_RE_UN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(un|und|unidade|unidades|caps|capsula|capsulas|dose|doses|sessoes|sessao|sessões|sessão|diaria|diarias|diária|diárias|noite|noites|peca|peça|pecas|peças|itens|item)\b")
_RE_M2 = re.compile(r"\b(\d+(?:\.\d+)?)\s*(m2|m²|metros quadrados)\b")


@functools.lru_cache(maxsize=16384)
def _normalizar_str(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s)
    cleaned = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = cleaned.lower()
    collapsed = _RE_SPACES.sub(" ", lowered)
    return collapsed.strip()


def normalizar(texto: Any) -> str:
    """Normaliza texto via NFKD, removendo acentos, convertendo para minúsculas e colapsando espaços."""
    if texto is None:
        return ""
    if isinstance(texto, str):
        return _normalizar_str(texto)
    return _normalizar_str(str(texto))


def remover_acentos(texto: Any) -> str:
    """Sanitiza strings para compatibilidade estrita com Latin-1 / Helvetica (FPDF)."""
    s = normalizar(texto)
    s = (s.replace("—", "-")
           .replace("–", "-")
           .replace("•", "-")
           .replace("“", '"')
           .replace("”", '"')
           .replace("’", "'"))
    return s.encode("latin-1", "ignore").decode("latin-1")


def termo(texto: str, consulta: str) -> bool:
    """Verifica correspondência exata de termo com boundary check semântico."""
    a, b = normalizar(texto), normalizar(consulta)
    if not b:
        return False
    return re.search(r"(?<!\w)" + re.escape(b) + r"(?!\w)", a) is not None


def truncar(texto: str, n: int) -> str:
    """Trunca texto de forma estável respeitando limites de palavras."""
    s = _RE_SPACES.sub(" ", str(texto or "")).strip()
    if len(s) <= n:
        return s
    return s[: max(20, n - 3)].rsplit(" ", 1)[0] + "..."


def parse_data(valor: Any) -> Optional[datetime]:
    """Interpreta múltiplos formatos de datas (ISO, BR, etc.)."""
    if not valor:
        return None
    s = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:30], fmt)
        except Exception:
            pass
    if date_parser:
        try:
            return date_parser.parse(s, fuzzy=False)
        except Exception:
            pass
    return None


def parse_money(value: Any) -> Optional[float]:
    """Extrai e converte valores monetários em formato numérico float."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("R$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(_RE_MONEY_CLEAN.sub("", s))
        return round(v, 2) if v >= 0 else None
    except Exception:
        return None


def normalizar_quantidade(unidade: str) -> Tuple[Optional[float], Optional[str]]:
    """Padroniza unidades de medida para equivalência matemática (ex: kg -> g, l -> ml, diárias/sessões -> un)."""
    if not unidade:
        return None, None
    n = normalizar(unidade).replace(",", ".")
    # 1. Pesos (canônico: g)
    m = _RE_KG.search(n)
    if m: return float(m.group(1)) * 1000.0, "g"
    m = _RE_G.search(n)
    if m: return float(m.group(1)), "g"
    m = _RE_MG.search(n)
    if m: return float(m.group(1)) / 1000.0, "g"

    # 2. Volumes (canônico: ml)
    m = _RE_L.search(n)
    if m: return float(m.group(1)) * 1000.0, "ml"
    m = _RE_ML.search(n)
    if m: return float(m.group(1)), "ml"

    # 3. Unidades / Contagens / Serviços (canônico: un)
    m = _RE_UN.search(n)
    if m: return float(m.group(1)), "un"

    # 4. Área (canônico: m2)
    m = _RE_M2.search(n)
    if m: return float(m.group(1)), "m2"

    return None, None


def nome_produto_normalizado(name: str) -> str:
    """Remove unidades e caracteres especiais para comparação fonética de produtos."""
    n = normalizar(name)
    n = _RE_PROD_UNITS.sub(" ", n)
    n = _RE_PROD_NON_ALNUM.sub(" ", n)
    return _RE_SPACES.sub(" ", n).strip()


def tokens_produto(name: str) -> Set[str]:
    """Gera conjunto de tokens significativos do produto sem stopwords."""
    stop = {"de", "da", "do", "e", "com", "sem", "para", "em", "tipo", "kit", "por", "cada", "mes", "ano"}
    return {x for x in nome_produto_normalizado(name).split() if len(x) > 2 and x not in stop}


def score_clamp(x: float) -> int:
    """Restringe estritamente scores no intervalo inteiro [0, 100]."""
    return max(0, min(100, int(round(x))))
