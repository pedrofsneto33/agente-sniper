# -*- coding: utf-8 -*-
"""
Módulo de Deltas Factuais e Comparação Temporal — Agente Sniper
Responsável por calcular variações entre coletas consecutivas de fontes e eventos sem acoplamento a banco de dados.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from domain.models import Fonte
from domain.identity import sha1
from domain.normalizer import parse_data
from domain.events import (
    EVENT_DATE_CLUSTER_DAYS,
    EVENT_CURRENT_WINDOW_DAYS,
    EVENT_CONTEXTUAL_MAX_DAYS,
    eventos_sao_mesmo_fato,
)

ESTADO_EVENTO_NOVO: str = "NOVO"
ESTADO_EVENTO_RECORRENTE: str = "RECORRENTE"
ESTADO_EVENTO_INATIVO_EXPIRADO: str = "INATIVO_EXPIRADO"


def calcular_delta_fontes(
    fontes: Sequence[Fonte],
    hashes_anteriores: Optional[Mapping[str, str]] = None
) -> Dict[str, Any]:
    """
    Calcula fontes novas e fontes alteradas em relação aos hashes da execução anterior.

    :param fontes: Sequência de fontes da execução atual.
    :param hashes_anteriores: Mapeamento {fingerprint: content_hash} da execução anterior, ou None se for a primeira execução.
    :return: Dicionário contendo a contagem e os conjuntos de fingerprints novos e alterados.
    """
    novos: Set[str] = set()
    alterados: Set[str] = set()

    if hashes_anteriores is not None:
        for f in fontes:
            if f.fingerprint not in hashes_anteriores:
                novos.add(f.fingerprint)
            elif hashes_anteriores[f.fingerprint] != sha1(f.conteudo):
                alterados.add(f.fingerprint)

    return {
        "novas_fontes": len(novos),
        "fontes_alteradas": len(alterados),
        "novos_fingerprints": novos,
        "alterados_fingerprints": alterados,
    }


def _extrair_data_evento(ev: Mapping[str, Any]) -> Optional[datetime]:
    """Extrai objeto datetime de um evento (date ou created_at)."""
    raw = ev.get("date") or ev.get("created_at") or ""
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw:
        return parse_data(raw[:10])
    return None


def calcular_delta_eventos(
    eventos_atuais: Sequence[Dict[str, Any]],
    eventos_historicos: Sequence[Dict[str, Any]],
    cluster_days: int = EVENT_DATE_CLUSTER_DAYS,
    hoje: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Classifica deterministicamente os eventos da execução atual em relação ao histórico.

    Ordem estrita de correspondência:
    1. event_key exato (para históricos ainda não consumidos)
    2. eventos_sao_mesmo_fato() (resolução semântico-temporal com limite cluster_days para históricos não consumidos)
    3. Ausência de correspondência -> NOVO

    Garante unicidade de pareamento 1-to-1 (um histórico pode ser consumido por no máximo 1 evento atual).
    Eventos históricos sem nova evidência que ultrapassaram EVENT_CURRENT_WINDOW_DAYS
    são identificados como INATIVO_EXPIRADO.
    """
    ref_hoje = hoje or datetime.now()

    novos: List[Dict[str, Any]] = []
    recorrentes: List[Dict[str, Any]] = []

    # Indexação histórica por event_key/event_id
    hist_por_key: Dict[str, Dict[str, Any]] = {}
    for h in eventos_historicos:
        k = h.get("event_key") or h.get("event_id")
        if k and k not in hist_por_key:
            hist_por_key[k] = h

    consumidos_hist_keys: Set[str] = set()

    for ev in eventos_atuais:
        ev_key = ev.get("event_key") or ev.get("event_id")
        pareado_hist = None

        # 1. Correspondência Exata por event_key (se não consumido)
        if ev_key and ev_key in hist_por_key and ev_key not in consumidos_hist_keys:
            pareado_hist = hist_por_key[ev_key]
        else:
            # 2. Resolução Semântico-Temporal (candidatos ainda não consumidos)
            for h in eventos_historicos:
                h_k = h.get("event_key") or h.get("event_id")
                if h_k and h_k in consumidos_hist_keys:
                    continue
                if eventos_sao_mesmo_fato(h, ev, cluster_days=cluster_days):
                    pareado_hist = h
                    break

        ev_copia = dict(ev)
        if pareado_hist is not None:
            h_k = pareado_hist.get("event_key") or pareado_hist.get("event_id")
            if h_k:
                consumidos_hist_keys.add(h_k)
            ev_copia["estado_temporal"] = ESTADO_EVENTO_RECORRENTE
            ev_copia["evento_origem_id"] = pareado_hist.get("event_id") or pareado_hist.get("event_key")
            recorrentes.append(ev_copia)
        else:
            ev_copia["estado_temporal"] = ESTADO_EVENTO_NOVO
            novos.append(ev_copia)

    # 3. Identificação de Históricos Expirados (> 45 dias sem nova evidência e não consumidos)
    expirados: List[Dict[str, Any]] = []
    for h in eventos_historicos:
        h_k = h.get("event_key") or h.get("event_id")
        if h_k and h_k in consumidos_hist_keys:
            continue

        dt_h = _extrair_data_evento(h)
        if dt_h:
            idade_dias = (ref_hoje.date() - dt_h.date()).days
            if idade_dias > EVENT_CURRENT_WINDOW_DAYS:
                h_exp = dict(h)
                h_exp["estado_temporal"] = ESTADO_EVENTO_INATIVO_EXPIRADO
                h_exp["idade_dias"] = idade_dias
                expirados.append(h_exp)

    total_ativos = len(novos) + len(recorrentes)
    taxa_renovacao = round(len(novos) / total_ativos, 4) if total_ativos > 0 else 0.0

    return {
        "novos": novos,
        "recorrentes": recorrentes,
        "expirados": expirados,
        "total_ativos": total_ativos,
        "taxa_renovacao": taxa_renovacao,
    }
