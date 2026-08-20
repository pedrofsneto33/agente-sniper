# -*- coding: utf-8 -*-
"""
Pacote de Provedores e Inteligência Generativa LLM — Agente Sniper
Reexporta os clientes de IA e formatadores de prompt.
"""
from __future__ import annotations

from llm.client import (
    CACHE,
    CACHE_TTL,
    build_system_prompt,
    chamar_gemini,
    chamar_groq,
    chamar_llm_json,
    chamar_ollama,
    gerar_inteligencia_llm,
    json_seguro,
)

__all__ = [
    "json_seguro",
    "build_system_prompt",
    "chamar_ollama",
    "chamar_gemini",
    "chamar_groq",
    "chamar_llm_json",
    "gerar_inteligencia_llm",
    "CACHE",
    "CACHE_TTL",
]
