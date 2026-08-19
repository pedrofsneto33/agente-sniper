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
        key = (str(x.get("entity") or ""), str(x.get("source_domain") or ""), str(x.get("product_key") or ""))
        old = precos_anteriores.get(key)
        if not old:
            continue

        old_price_raw, old_promo = old[0], old[1]
        new_price_raw = x.get("price")

        # Validação robusta contra tipos inválidos e valores nulos
        if old_price_raw is None or new_price_raw is None:
            continue

        try:
            old_price = float(old_price_raw)
            new_price = float(new_price_raw)
        except (ValueError, TypeError):
            continue

        # Preço histórico não-positivo é inválido para cálculo percentual
        if old_price <= 0:
            continue

        pct = (new_price - old_price) / old_price * 100.0
        promo_changed = bool(x.get("promotion")) != bool(old_promo)

        if abs(pct) >= min_change_pct or promo_changed:
            changes.append({
                "entity": x.get("entity"),
                "source_domain": x.get("source_domain"),
                "product_key": x.get("product_key"),
                "product_name": x.get("product_name"),
                "previous_price": old_price_raw,
                "current_price": new_price_raw,
                "change_pct": round(pct, 2),
                "promotion_before": old_promo,
                "promotion_now": bool(x.get("promotion")),
                "url": x.get("url", "")
            })

    # Ordenação determinística: maior magnitude percentual primeiro, depois entidade, depois chave do produto
    changes.sort(key=lambda item: (
        -abs(item["change_pct"]),
        str(item.get("entity") or ""),
        str(item.get("product_key") or "")
    ))

    return changes[:max_mudancas]
