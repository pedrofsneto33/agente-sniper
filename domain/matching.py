# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Algoritmos de Matching e Similaridade de Catálogos.
Lógica pura de domínio sem I/O, rede ou banco.
"""
import difflib
import re
from typing import Set

from domain.models import PriceItem
from domain.normalizer import (
    normalizar,
    nome_produto_normalizado,
    tokens_produto,
    normalizar_quantidade,
)


def _extrair_numeros_relevantes(name: str) -> Set[str]:
    """Extrai números identificadores no título que não sejam meras pontuações."""
    n = normalizar(name).replace(",", ".")
    return set(re.findall(r"\b\d+(?:\.\d+)?\b", n))


def similaridade_produto(a: PriceItem, b: PriceItem) -> float:
    """Calcula a similaridade fuzzy entre dois itens considerando tokens, marca, quantidade/volume e SKU."""
    norm_a, norm_b = nome_produto_normalizado(a.name), nome_produto_normalizado(b.name)
    ta, tb = tokens_produto(a.name), tokens_produto(b.name)
    seq = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
    overlap = len(ta & tb) / max(1, len(ta | tb)) if ta and tb else seq
    score = 0.64 * overlap + 0.24 * seq

    # 1. Bônus de marca
    if a.brand and b.brand and normalizar(a.brand) == normalizar(b.brand):
        score += 0.14

    # 2. Extração de quantidade: tenta do campo unit; se ausente, extrai do próprio nome
    qa, ua = normalizar_quantidade(a.unit)
    if qa is None:
        qa, ua = normalizar_quantidade(a.name)

    qb, ub = normalizar_quantidade(b.unit)
    if qb is None:
        qb, ub = normalizar_quantidade(b.name)

    # 3. Avaliação estrita de quantidade e volume
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

    # 4. Verificação de números e atributos de plano no título (quando não consumidos por unidade)
    nums_a = _extrair_numeros_relevantes(a.name)
    nums_b = _extrair_numeros_relevantes(b.name)
    if nums_a and nums_b and qa is None and qb is None:
        num_overlap = len(nums_a & nums_b) / max(len(nums_a | nums_b), 1)
        if num_overlap < 1.0:
            score -= 0.30 * (1.0 - num_overlap)

    # 5. Bônus de nomes idênticos
    if norm_a and norm_b and norm_a == norm_b and normalizar(a.name) == normalizar(b.name):
        score += 0.12

    # 6. Bônus de SKU idêntico
    if a.sku and b.sku and normalizar(a.sku) == normalizar(b.sku):
        score += 0.35

    return max(0.0, min(1.0, score))
