# -*- coding: utf-8 -*-
"""
Pacote de Apresentação e Relatórios — Agente Sniper
Exporta os renderizadores e serializadores do sistema.
"""
from __future__ import annotations

from reports.html import (
    ref_text,
    fonte_por_id,
    html_escape,
    rotulo_dimensao,
    gerar_html,
)
from reports.pdf import gerar_pdf
from reports.export import (
    salvar_json,
    salvar_csv_fontes,
)

__all__ = [
    "ref_text",
    "fonte_por_id",
    "html_escape",
    "rotulo_dimensao",
    "gerar_html",
    "gerar_pdf",
    "salvar_json",
    "salvar_csv_fontes",
]
