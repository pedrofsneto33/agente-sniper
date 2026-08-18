# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Normalização e Sanitização Textual / Numérica.
Lógica de domínio pura sem I/O, rede, banco ou estado global.
"""
import re
import unicodedata
from datetime import datetime
from typing import Any, Optional, Tuple, Set

try:
    from dateutil import parser as date_parser
except ImportError:
    date_parser = None


def normalizar(texto: Any) -> str:
    """Normaliza texto via NFKD, removendo acentos, convertendo para minúsculas e colapsando espaços."""
    if texto is None:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


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
    s = re.sub(r"\s+", " ", str(texto or "")).strip()
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
        v = float(re.sub(r"[^0-9.\-]", "", s))
        return round(v, 2) if v >= 0 else None
    except Exception:
        return None


def normalizar_quantidade(unidade: str) -> Tuple[Optional[float], Optional[str]]:
    """Padroniza unidades de medida para equivalência matemática (ex: kg -> g, l -> ml)."""
    n = normalizar(unidade).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|mg|l|ml|un|und|unidade|unidades|m2|m²)", n)
    if not m:
        return None, None
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "kg": return val * 1000, "g"
    if unit == "mg": return val / 1000, "g"
    if unit == "l": return val * 1000, "ml"
    if unit in {"un", "und", "unidade", "unidades"}: return val, "un"
    if unit in {"m2", "m²"}: return val, "m2"
    return val, unit


def nome_produto_normalizado(name: str) -> str:
    """Remove unidades e caracteres especiais para comparação fonética de produtos."""
    n = normalizar(name)
    n = re.sub(r"\b\d+(?:[\.,]\d+)?\s*(kg|g|mg|l|ml|un|und|unidade|unidades|m2|m²)\b", " ", n)
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def tokens_produto(name: str) -> Set[str]:
    """Gera conjunto de tokens significativos do produto sem stopwords."""
    stop = {"de", "da", "do", "e", "com", "sem", "para", "em", "tipo", "kit"}
    return {x for x in nome_produto_normalizado(name).split() if len(x) > 2 and x not in stop}


def score_clamp(x: float) -> int:
    """Restringe estritamente scores no intervalo inteiro [0, 100]."""
    return max(0, min(100, int(round(x))))
