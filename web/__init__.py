# -*- coding: utf-8 -*-
"""
Pacote de Navegação e Extração Web — Agente Sniper
Reexporta o gerenciador persistente de Playwright, funções de extração de páginas e enriquecimento concorrente.
"""
from __future__ import annotations

from web.browser import PersistentPlaywrightManager
from web.extractor import (
    enriquecer,
    extrair_html,
    extrair_pagina,
    extrair_playwright,
)

__all__ = [
    "PersistentPlaywrightManager",
    "extrair_html",
    "extrair_playwright",
    "extrair_pagina",
    "enriquecer",
]
