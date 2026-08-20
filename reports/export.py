# -*- coding: utf-8 -*-
"""
Camada de Exportação de Dados — Agente Sniper
Serialização e persistência de artefatos estruturados em JSON e CSV.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, List, Optional

from domain.models import Fonte


def salvar_json(nome: str, obj: Any, pasta_execucao: Optional[Path] = None) -> str:
    """
    Serializa objeto para arquivo JSON formatado em UTF-8.
    """
    pasta = pasta_execucao or Path("sniper_resultados")
    pasta.mkdir(parents=True, exist_ok=True)
    path = pasta / nome
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(path.resolve())


def salvar_csv_fontes(fontes: List[Fonte], pasta_execucao: Optional[Path] = None) -> str:
    """
    Exporta lista de fontes auditáveis para CSV delimitado por ponto-e-vírgula em UTF-8 com BOM.
    """
    pasta = pasta_execucao or Path("sniper_resultados")
    pasta.mkdir(parents=True, exist_ok=True)
    path = pasta / "fontes.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ID", "Categoria", "Titulo", "URL", "Data", "Origem", "Escopo", "Atual", "Score", "Confianca"])
        for x in fontes:
            w.writerow([x.id, x.categoria, x.titulo, x.url, x.data_publicacao, x.origem, x.escopo, x.atual, round(x.score, 1), round(x.confianca, 3)])
    return str(path.resolve())
