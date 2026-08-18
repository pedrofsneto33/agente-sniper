# -*- coding: utf-8 -*-
"""
Módulo de Deltas Factuais e Comparação Temporal — Agente Sniper
Responsável por calcular variações entre coletas consecutivas de fontes sem acoplamento a banco de dados.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Set

from domain.models import Fonte
from domain.identity import sha1


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
