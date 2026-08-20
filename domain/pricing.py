# -*- coding: utf-8 -*-
"""
Módulo de Precificação e Inteligência de Preços — Agente Sniper
Responsável por calcular variações percentuais de preços, alternância promocional,
séries temporais históricas, volatilidade e deltas de mercado sem dependências de infraestrutura.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from domain.normalizer import parse_data


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


def calcular_serie_temporal_precos(
    snapshots_historicos: Sequence[Mapping[str, Any]],
    janelas_dias: Sequence[int] = (7, 15, 30),
    hoje: Optional[datetime] = None,
    min_change_pct: float = 0.5
) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """
    Calcula séries temporais, médias, volatilidade e variações por janela para cada produto.

    :param snapshots_historicos: Sequência de snapshots de preço de múltiplas runs.
    :param janelas_dias: Tupla de janelas em dias para cálculo de deltas (default: 7, 15, 30).
    :param hoje: Data de referência opcional para ancoragem de janelas.
    :param min_change_pct: Limiar percentual para definir tendência (default: 0.5%).
    :return: Mapeamento {(entity, source_domain, product_key): resumo_serie}.
    """
    if not snapshots_historicos:
        return {}

    # Agrupamento e validação de pontos
    grupos: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}

    for s in snapshots_historicos:
        # Extração e validação do preço
        price_raw = s.get("price")
        if price_raw is None:
            continue
        try:
            price = float(price_raw)
        except (ValueError, TypeError):
            continue
        if price <= 0:
            continue

        # Extração da data / timestamp
        raw_date = s.get("captured_at") or s.get("created_at") or s.get("date") or ""
        dt: Optional[datetime] = None
        if isinstance(raw_date, datetime):
            dt = raw_date
        elif isinstance(raw_date, str) and raw_date.strip():
            dt = parse_data(raw_date[:19])
            if dt is None:
                try:
                    dt = datetime.fromisoformat(raw_date.strip())
                except Exception:
                    dt = None

        if dt is None:
            continue

        entity = str(s.get("entity") or "")
        source_domain = str(s.get("source_domain") or "")
        product_key = str(s.get("product_key") or "")
        key = (entity, source_domain, product_key)

        if not any(key):
            continue

        data_str = dt.strftime("%Y-%m-%d %H:%M:%S") if (dt.hour or dt.minute or dt.second) else dt.strftime("%Y-%m-%d")

        ponto = {
            "dt": dt,
            "data_str": data_str,
            "price": price,
            "promotion": bool(s.get("promotion")),
            "product_name": str(s.get("product_name") or ""),
            "brand": str(s.get("brand") or ""),
            "unit": str(s.get("unit") or ""),
            "url": str(s.get("url") or ""),
        }
        grupos.setdefault(key, []).append(ponto)

    resultado: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for key, pontos in grupos.items():
        if not pontos:
            continue

        # Ordenação determinística com desempate
        pontos.sort(key=lambda p: (
            p["dt"],
            p["price"],
            p["url"],
            p["product_name"]
        ))

        N = len(pontos)
        last = pontos[-1]
        preco_atual = last["price"]
        preco_anterior = pontos[-2]["price"] if N >= 2 else None

        variacao_imediata_pct: Optional[float] = None
        if preco_anterior is not None and preco_anterior > 0:
            variacao_imediata_pct = round((preco_atual - preco_anterior) / preco_anterior * 100.0, 2)

        precos = [p["price"] for p in pontos]
        preco_min = min(precos)
        preco_max = max(precos)
        media_preco = round(sum(precos) / N, 2)

        # Volatilidade (Desvio padrão amostral s)
        if N < 2:
            volatilidade = 0.0
        else:
            media_calc = sum(precos) / N
            variancia = sum((p - media_calc) ** 2 for p in precos) / (N - 1)
            volatilidade = round(math.sqrt(variancia), 4)

        # Tendência global (primeiro vs último ponto válido)
        if N < 2:
            tendencia = "INSUFICIENTE"
        else:
            p_inicial = pontos[0]["price"]
            if p_inicial > 0:
                delta_global = (preco_atual - p_inicial) / p_inicial * 100.0
                if delta_global > min_change_pct:
                    tendencia = "ALTA"
                elif delta_global < -min_change_pct:
                    tendencia = "QUEDA"
                else:
                    tendencia = "ESTAVEL"
            else:
                tendencia = "INSUFICIENTE"

        # Janelas temporais
        ref_dt = hoje or last["dt"]
        deltas_janela: Dict[int, Optional[float]] = {}

        for W in janelas_dias:
            limite_inicio = ref_dt - timedelta(days=W)
            # Pontos históricos anteriores ao atual dentro da janela: [limite_inicio, ref_dt]
            pontos_na_janela = [
                p for p in pontos[:-1]
                if limite_inicio <= p["dt"] <= ref_dt
            ]
            if pontos_na_janela:
                p_base = pontos_na_janela[0]["price"]
                if p_base > 0:
                    deltas_janela[W] = round((preco_atual - p_base) / p_base * 100.0, 2)
                else:
                    deltas_janela[W] = None
            else:
                deltas_janela[W] = None

        serie_historica = [
            {
                "data": p["data_str"],
                "price": p["price"],
                "promotion": p["promotion"]
            }
            for p in pontos
        ]

        resultado[key] = {
            "entity": key[0],
            "source_domain": key[1],
            "product_key": key[2],
            "product_name": last["product_name"],
            "brand": last["brand"],
            "unit": last["unit"],
            "preco_atual": preco_atual,
            "preco_anterior": preco_anterior,
            "variacao_imediata_pct": variacao_imediata_pct,
            "preco_min": preco_min,
            "preco_max": preco_max,
            "media_preco": media_preco,
            "volatilidade": volatilidade,
            "tendencia": tendencia,
            "pontos_observados": N,
            "deltas_janela": deltas_janela,
            "serie_historica": serie_historica
        }

    return resultado
