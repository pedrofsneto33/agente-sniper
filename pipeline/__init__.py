"""
Pacote Pipeline — Agente Sniper (Fases 43B-44).
Exporta executores de replay offline, orquestração e ingestão concorrente.
"""

from pipeline.replay import (
    OfflineNetworkGuard,
    resolver_fixture_fontes_offline,
    executar_replay_offline,
)
from pipeline.ingestion import (
    coletar_tudo,
    enriquecer,
)

__all__ = [
    "OfflineNetworkGuard",
    "resolver_fixture_fontes_offline",
    "executar_replay_offline",
    "coletar_tudo",
    "enriquecer",
]
