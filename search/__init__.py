# -*- coding: utf-8 -*-
"""
Pacote de Busca e Coleta Web — Agente Sniper
Reexporta os provedores de busca, gerador de consultas e despachante concorrente.
"""
from __future__ import annotations

from search.providers import (
    TavilyBudgetGuard,
    buscar_ddg,
    buscar_news_rss,
    buscar_tavily,
    coletar_tudo,
    gerar_consultas,
)

__all__ = [
    "TavilyBudgetGuard",
    "gerar_consultas",
    "buscar_tavily",
    "buscar_ddg",
    "buscar_news_rss",
    "coletar_tudo",
]
