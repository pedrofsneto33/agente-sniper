"""
Módulo de Ingestão e Enriquecimento Concorrente — Agente Sniper (Fase 44).
Orquestra a busca multi-provedor concorrente e o enriquecimento de páginas web
com injeção de dependências e telemetria transparente.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from domain.models import Fonte
from domain.normalizer import parse_data
from domain.sources import sinais_deterministicos, score_fonte, _alias_empresa
from domain.identity import cidade_ok, estado_ok
from search.providers import (
    gerar_consultas,
    coletar_tudo as _search_coletar_tudo,
    _TAVILY_GUARD,
    TavilyBudgetGuard,
)
from web.extractor import (
    enriquecer as _web_enriquecer,
    PersistentPlaywrightManager,
    _PLAYWRIGHT_MGR,
)

logger = logging.getLogger("agente_sniper.pipeline.ingestion")

# Defaults operacionais de ambiente
DISCOVERY_MAX_WORKERS_DEFAULT = 16
ENRICH_MAX_WORKERS_DEFAULT = 8
MAX_ENRIQUECIMENTO_DEFAULT = 30
MAX_FONTES_FINAIS_DEFAULT = 50


def coletar_tudo(
    tavily_client: Any = None,
    consultas: Optional[Dict[str, List[Tuple[str, str]]]] = None,
    max_consultas_por_grupo: Optional[int] = None,
    usar_tavily: Optional[bool] = None,
    usar_ddg: Optional[bool] = None,
    usar_news_rss: Optional[bool] = None,
    max_workers: Optional[int] = None,
    guard: Optional[TavilyBudgetGuard] = None,
    session: Optional[requests.Session] = None,
    io_stats: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Orquestra a coleta multi-provedor concorrente com contabilidade de tarefas e telemetria.
    """
    consultas_map = consultas if consultas is not None else gerar_consultas()
    max_por_grupo = max_consultas_por_grupo if max_consultas_por_grupo is not None else int(os.getenv("MAX_CONSULTAS_POR_GRUPO", "5"))
    flag_tavily = (os.getenv("USAR_TAVILY", "1") == "1") if usar_tavily is None else usar_tavily
    flag_ddg = (os.getenv("USAR_DDG", "1") == "1") if usar_ddg is None else usar_ddg
    flag_rss = (os.getenv("USAR_NEWS_RSS", "1") == "1") if usar_news_rss is None else usar_news_rss
    n_workers = max_workers if max_workers is not None else int(os.getenv("DISCOVERY_MAX_WORKERS", str(DISCOVERY_MAX_WORKERS_DEFAULT)))
    t_guard = guard or _TAVILY_GUARD

    flat_tasks_count = 0
    for grupo, itens in consultas_map.items():
        itens_exec = itens[:max_por_grupo]
        for _ in itens_exec:
            if flag_tavily and tavily_client:
                flat_tasks_count += 1
            if flag_ddg:
                flat_tasks_count += 1
            if flag_rss:
                flat_tasks_count += 1

    if io_stats is not None:
        io_stats["discovery_tasks"] = flat_tasks_count

    t_start = time.perf_counter()

    todas = _search_coletar_tudo(
        tavily_client=tavily_client,
        consultas=consultas_map,
        max_consultas_por_grupo=max_por_grupo,
        usar_tavily=flag_tavily,
        usar_ddg=flag_ddg,
        usar_news_rss=flag_rss,
        max_workers=n_workers,
        guard=t_guard,
        session=session,
    )

    t_elapsed = time.perf_counter() - t_start
    if io_stats is not None:
        io_stats["discovery_time"] = t_elapsed

    logger.info("[COLETA] %d resultados brutos coletados em %.2fs", len(todas), t_elapsed)
    return todas


def enriquecer(
    fontes: List[Fonte],
    max_enriquecimento: Optional[int] = None,
    max_workers: Optional[int] = None,
    max_fontes_finais: Optional[int] = None,
    mgr: Optional[PersistentPlaywrightManager] = None,
    session: Optional[requests.Session] = None,
    parse_data_fn: Optional[Callable[[str], Any]] = None,
    alias_empresa_fn: Optional[Callable[[str], Optional[str]]] = None,
    cidade_ok_fn: Optional[Callable[[str], bool]] = None,
    estado_ok_fn: Optional[Callable[[str], bool]] = None,
    sinais_fn: Optional[Callable[[str], List[str]]] = None,
    score_fonte_fn: Optional[Callable[[Fonte], float]] = None,
    io_stats: Optional[Dict[str, Any]] = None,
) -> List[Fonte]:
    """
    Orquestra o enriquecimento concorrente das principais fontes com extração web e telemetria.
    """
    n_enrich = max_enriquecimento if max_enriquecimento is not None else int(os.getenv("MAX_ENRIQUECIMENTO", str(MAX_ENRIQUECIMENTO_DEFAULT)))
    n_workers = max_workers if max_workers is not None else int(os.getenv("ENRICH_MAX_WORKERS", str(ENRICH_MAX_WORKERS_DEFAULT)))
    n_finais = max_fontes_finais if max_fontes_finais is not None else int(os.getenv("MAX_FONTES_FINAIS", str(MAX_FONTES_FINAIS_DEFAULT)))
    playwright_mgr = mgr or _PLAYWRIGHT_MGR

    alvo_count = min(len(fontes), n_enrich)
    if io_stats is not None:
        io_stats["enrich_tasks"] = alvo_count

    t_start = time.perf_counter()

    res = _web_enriquecer(
        fontes=fontes,
        max_enriquecimento=n_enrich,
        max_workers=n_workers,
        max_fontes_finais=n_finais,
        mgr=playwright_mgr,
        session=session,
        parse_data_fn=parse_data_fn or parse_data,
        alias_empresa_fn=alias_empresa_fn or _alias_empresa,
        cidade_ok_fn=cidade_ok_fn or cidade_ok,
        estado_ok_fn=estado_ok_fn or estado_ok,
        sinais_fn=sinais_fn or sinais_deterministicos,
        score_fonte_fn=score_fonte_fn or score_fonte,
    )

    t_elapsed = time.perf_counter() - t_start
    if io_stats is not None:
        io_stats["enrich_time"] = t_elapsed

    logger.info("[ENRIQUECIMENTO] %d fontes enriquecidas em %.2fs", alvo_count, t_elapsed)
    return res


__all__ = [
    "coletar_tudo",
    "enriquecer",
]
