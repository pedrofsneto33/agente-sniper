# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Identidade Empresarial, Geográfica e de URLs.
Funções puras sem acoplamento a variáveis globais de ambiente.
"""
import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Tuple
from urllib.parse import urlparse, urlunparse

from domain.normalizer import normalizar, termo, parse_data


def sha1(texto: str) -> str:
    """Gera hash SHA-1 determinístico."""
    return hashlib.sha1(str(texto or "").encode("utf-8", errors="ignore")).hexdigest()


def url_normalizada(url: str) -> str:
    """Higieniza URLs removendo parâmetros de rastreamento (UTM, gclid, etc.)."""
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
        scheme = (p.scheme or "https").lower()
        host = p.netloc.lower().replace("www.", "")
        path = re.sub(r"/{2,}", "/", p.path or "/").rstrip("/") or "/"
        keep = []
        for q in (p.query or "").split("&"):
            if not q:
                continue
            k = q.split("=", 1)[0].lower()
            if k.startswith("utm_") or k in {"gclid", "fbclid", "msclkid"}:
                continue
            keep.append(q)
        return urlunparse((scheme, host, path, "", "&".join(keep), ""))
    except Exception:
        return url.strip()


def dominio(url: str) -> str:
    """Extrai o domínio limpo (sem www) de uma URL."""
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def data_na_url(url: str) -> Optional[datetime]:
    """Identifica padrões de datas embutidos na URL."""
    for pattern in (
        r"/(20\d{2})/(0[1-9]|1[0-2])/([0-3]\d)(?:/|$)",
        r"/(20\d{2})-(0[1-9]|1[0-2])-([0-3]\d)(?:/|$)",
    ):
        m = re.search(pattern, url or "")
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return None


def data_publicacao(raw: Dict[str, Any]) -> Tuple[str, str, Optional[datetime]]:
    """Extrai a data de publicação a partir de metadados ou URL."""
    d = parse_data(raw.get("data_publicacao", ""))
    if d:
        return d.strftime("%Y-%m-%d"), "publicada", d
    d = data_na_url(raw.get("url", ""))
    if d:
        return d.strftime("%Y-%m-%d"), "url", d
    return "", "desconhecida", None


def cidade_ok(texto: str, cidade: str = "") -> bool:
    """Valida se o texto referencia a cidade especificada com boundary check."""
    return bool(cidade) and termo(texto, cidade)


def estado_ok(texto: str, estado: str = "") -> bool:
    """Valida se o texto referencia a sigla ou nome do estado especificado."""
    n = normalizar(texto)
    est = normalizar(estado)
    if not est:
        return False
    if len(est) <= 2:
        return bool(re.search(r"(?<!\w)" + re.escape(est) + r"(?!\w)", n))
    return termo(n, est)


def identidade_conflitante(
    texto: str,
    empresa_alvo: str = "",
    termos_conflitantes: Optional[Sequence[str]] = None
) -> bool:
    """
    Detecta homônimos em ramos conflitantes a partir de uma política configurada de termos de exclusão.
    Retorna False caso nenhuma lista de termos conflitantes seja fornecida.
    """
    if not termos_conflitantes:
        return False
    n = normalizar(texto)
    return any(normalizar(x) in n for x in termos_conflitantes if x)
