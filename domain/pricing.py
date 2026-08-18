# -*- coding: utf-8 -*-
"""
Módulo de Precificação e Inteligência de Preços — Agente Sniper
Responsável por calcular variações percentuais de preços, alternância promocional e deltas de mercado sem dependências de infraestrutura.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def detectar_mudancas_preco(
    snapshots: Sequence[Mapping[str, Any]],
    precos_anteriores: Optional[Mapping[Tuple[str, str, str], Tuple[Optional[float], bool]]] = None,
    min_change_pct: float = 0.5,
    max_mudancas: int = 100
) -> List[Dict[str, Any]]:
    """
    Calcula mudanças de preços e promoções comparando snapshots atuais com o histórico anterior.

    :param snapshots: Sequência de dicionários de snapshots da execução atual.
    :param precos_anteriores: Mapeamento {(entity, source_domain, product_key): (price, promotion)} da execução anterior.
    :param min_change_pct: Limiar percentual mínimo para considerar uma mudança relevante (default 0.5%).
    :param max_mudancas: Limite máximo de mudanças retornadas (default 100).
    :return: Lista de dicionários contendo os detalhes das mudanças detectadas.
    """
    if not precos_anteriores:
        return []

    changes: List[Dict[str, Any]] = []

    for x in snapshots:
        key = (x.get("entity", ""), x.get("source_domain", ""), x.get("product_key", ""))
        old = precos_anteriores.get(key)
        if old and x.get("price") is not None and old[0] not in (None, 0):
            pct = (float(x["price"]) - float(old[0])) / float(old[0]) * 100
            promo_changed = bool(x.get("promotion")) != old[1]
            if abs(pct) >= min_change_pct or promo_changed:
                changes.append({
                    "entity": x.get("entity"),
                    "source_domain": x.get("source_domain"),
                    "product_key": x.get("product_key"),
                    "product_name": x.get("product_name"),
                    "previous_price": old[0],
                    "current_price": x.get("price"),
                    "change_pct": round(pct, 2),
                    "promotion_before": old[1],
                    "promotion_now": bool(x.get("promotion")),
                    "url": x.get("url", "")
                })

    return changes[:max_mudancas]
