# -*- coding: utf-8 -*-
"""
Pacote de Domínio — Agente Sniper
Camada de lógica de negócio pura, modelos de dados e regras canônicas sem dependências de infraestrutura.
"""

from domain.models import Fonte, PriceItem
from domain.normalizer import (
    normalizar,
    remover_acentos,
    termo,
    truncar,
    parse_data,
    parse_money,
    normalizar_quantidade,
    nome_produto_normalizado,
    tokens_produto,
    score_clamp,
)
from domain.identity import (
    sha1,
    url_normalizada,
    dominio,
    data_na_url,
    data_publicacao,
    cidade_ok,
    estado_ok,
    identidade_conflitante,
)
from domain.matching import similaridade_produto
from domain.events import (
    EVENT_RULES,
    RISK_KINDS,
    OPPORTUNITY_KINDS,
    recencia_score,
    qualidade_fonte,
    evento_titulo_estavel,
    canonical_event_key,
    _primary_event_kind,
    eventos_sao_mesmo_fato,
    criar_eventos,
)
from domain.deltas import calcular_delta_fontes

__all__ = [
    "Fonte",
    "PriceItem",
    "normalizar",
    "remover_acentos",
    "termo",
    "truncar",
    "parse_data",
    "parse_money",
    "normalizar_quantidade",
    "nome_produto_normalizado",
    "tokens_produto",
    "score_clamp",
    "sha1",
    "url_normalizada",
    "dominio",
    "data_na_url",
    "data_publicacao",
    "cidade_ok",
    "estado_ok",
    "identidade_conflitante",
    "similaridade_produto",
    "EVENT_RULES",
    "RISK_KINDS",
    "OPPORTUNITY_KINDS",
    "recencia_score",
    "qualidade_fonte",
    "evento_titulo_estavel",
    "canonical_event_key",
    "_primary_event_kind",
    "eventos_sao_mesmo_fato",
    "criar_eventos",
    "calcular_delta_fontes",
]
