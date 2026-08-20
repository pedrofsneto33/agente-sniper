# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Algoritmos de Matching e Similaridade de Catálogos.
Lógica pura de domínio sem I/O, rede ou banco.
"""
import difflib
import functools
import re
from typing import Optional, Set, Tuple

from domain.models import PriceItem
from domain.normalizer import (
    normalizar,
    nome_produto_normalizado,
    tokens_produto,
    normalizar_quantidade,
)


@functools.lru_cache(maxsize=4096)
def _extrair_numeros_relevantes(name: str) -> Set[str]:
    """Extrai números identificadores no título que não sejam meras pontuações."""
    n = normalizar(name).replace(",", ".")
    return set(re.findall(r"\b\d+(?:\.\d+)?\b", n))


@functools.lru_cache(maxsize=4096)
def _item_profile(name: str, brand: str, unit: str, sku: str) -> Tuple[str, Set[str], Optional[float], Optional[str], Set[str], str, str, str]:
    """Pré-computa todas as propriedades invariantes de um PriceItem."""
    norm_name = nome_produto_normalizado(name)
    tokens = tokens_produto(name)
    q, u = normalizar_quantidade(unit)
    if q is None:
        q, u = normalizar_quantidade(name)
    nums = _extrair_numeros_relevantes(name)
    norm_brand = normalizar(brand) if brand else ""
    norm_full_name = normalizar(name) if name else ""
    norm_sku = normalizar(sku) if sku else ""
    return norm_name, tokens, q, u, nums, norm_brand, norm_full_name, norm_sku


@functools.lru_cache(maxsize=8192)
def _seq_ratio(norm_a: str, norm_b: str) -> float:
    """Calcula ou recupera em cache o ratio fuzzy entre dois nomes normalizados."""
    if norm_a == norm_b:
        return 1.0
    if not norm_a or not norm_b:
        return 0.0
    return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()


def similaridade_produto(a: PriceItem, b: PriceItem) -> float:
    """Calcula a similaridade fuzzy entre dois itens considerando tokens, marca, quantidade/volume e SKU."""
    norm_a, ta, qa, ua, nums_a, brand_a, fname_a, sku_a = _item_profile(
        str(a.name) if a.name is not None else "",
        str(a.brand) if a.brand is not None else "",
        str(a.unit) if a.unit is not None else "",
        str(a.sku) if a.sku is not None else ""
    )
    norm_b, tb, qb, ub, nums_b, brand_b, fname_b, sku_b = _item_profile(
        str(b.name) if b.name is not None else "",
        str(b.brand) if b.brand is not None else "",
        str(b.unit) if b.unit is not None else "",
        str(b.sku) if b.sku is not None else ""
    )

    seq = _seq_ratio(norm_a, norm_b)
    overlap = len(ta & tb) / max(1, len(ta | tb)) if ta and tb else seq
    score = 0.64 * overlap + 0.24 * seq

    # 1. Bônus de marca
    if brand_a and brand_b and brand_a == brand_b:
        score += 0.14

    # 2. Avaliação estrita de quantidade e volume
    if qa is not None and qb is not None:
        if ua == ub:
            if abs(qa - qb) < 1e-6:
                score += 0.18  # Mesma quantidade normalizada (ex: 500g vs 0.5kg)
            else:
                # Quantidades incompatíveis na mesma unidade (ex: 500g vs 250g, 500ml vs 1L)
                # Penalização proporcional forte para impedir falso matching
                ratio = min(qa, qb) / max(qa, qb)
                score -= 0.50 * (1.0 - ratio) + 0.25
        else:
            # Unidades incompatíveis (ex: 500g vs 500ml)
            score -= 0.45
    elif (a.unit and b.unit) and (qa is None or qb is None):
        # Ambos têm unit textual mas não padronizável
        score -= 0.08

    # 3. Verificação de números e atributos de plano no título (quando não consumidos por unidade)
    if nums_a and nums_b and qa is None and qb is None:
        num_overlap = len(nums_a & nums_b) / max(len(nums_a | nums_b), 1)
        if num_overlap < 1.0:
            score -= 0.30 * (1.0 - num_overlap)

    # 4. Bônus de nomes idênticos
    if norm_a and norm_b and norm_a == norm_b and fname_a == fname_b:
        score += 0.12

    # 5. Bônus de SKU idêntico
    if sku_a and sku_b and sku_a == sku_b:
        score += 0.35

    return max(0.0, min(1.0, score))
