# -*- coding: utf-8 -*-
"""
Módulo de Domínio — Algoritmos de Matching e Similaridade de Catálogos.
Lógica pura de domínio sem I/O, rede ou banco.
"""
import difflib
from domain.models import PriceItem
from domain.normalizer import (
    normalizar,
    nome_produto_normalizado,
    tokens_produto,
    normalizar_quantidade,
)


def similaridade_produto(a: PriceItem, b: PriceItem) -> float:
    """Calcula a similaridade fuzzy entre dois itens considerando tokens, marca, unidade e SKU."""
    ta, tb = tokens_produto(a.name), tokens_produto(b.name)
    seq = difflib.SequenceMatcher(None, nome_produto_normalizado(a.name), nome_produto_normalizado(b.name)).ratio()
    overlap = len(ta & tb) / max(1, len(ta | tb)) if ta and tb else seq
    score = 0.64 * overlap + 0.24 * seq
    if a.brand and b.brand and normalizar(a.brand) == normalizar(b.brand):
        score += 0.14
    qa, ua = normalizar_quantidade(a.unit)
    qb, ub = normalizar_quantidade(b.unit)
    if qa is not None and qb is not None and ua == ub:
        score += 0.18 if abs(qa - qb) < 1e-6 else -0.18
    elif a.unit and b.unit:
        score -= 0.08
    if a.sku and b.sku and normalizar(a.sku) == normalizar(b.sku):
        score += 0.35
    return max(0.0, min(1.0, score))
