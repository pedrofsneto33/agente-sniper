# -*- coding: utf-8 -*-
"""
M?dulo de Observabilidade Operacional do Motor Generic ? Fase 8
Fornece rastreamento, agrega??o de m?tricas e persist?ncia append-only em JSONL
sem interfer?ncia no fluxo de neg?cio, sem depend?ncia bloqueante e sem alterar o banco SQLite.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from extractors.canary import percentil
from extractors.promotion_gate import calcular_sha256_arquivo, SQLITE_CANONICAL_HASH

logger = logging.getLogger("extractors.observability")

OPERATIONAL_METRICS_PATH = Path(r"C:\Users\User\Desktop\Agente sniper\dados_browser\operational_metrics.jsonl")


@dataclass
class OperationalRunRecord:
    """Registro estruturado de uma observa??o ou execu??o operacional do extrator."""
    run_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    engine: str = "generic"
    source: str = "Assai"
    document_id: str = ""
    document_hash: str = ""
    extraction: Dict[str, Any] = field(default_factory=dict)
    quality: Dict[str, Any] = field(default_factory=dict)
    reliability: Dict[str, Any] = field(default_factory=dict)
    performance: Dict[str, Any] = field(default_factory=dict)
    downstream: Dict[str, Any] = field(default_factory=dict)
    integrity: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OperationalMetricsTracker:
    """Gerenciador de observabilidade e m?tricas operacionais append-only."""

    def __init__(self, log_path: Optional[Union[str, Path]] = None):
        self.log_path = Path(log_path or OPERATIONAL_METRICS_PATH)
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def registrar_execucao(self, record: OperationalRunRecord) -> bool:
        """
        Persiste um registro de observabilidade de forma fail-safe e n?o bloqueante.
        Retorna True se persistido com sucesso, False se falhar (sem lan?ar exce??es para o chamador).
        """
        try:
            linha = json.dumps(record.to_dict(), ensure_ascii=False)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
            return True
        except Exception as e:
            logger.warning("[OBSERVABILIDADE] Falha ao registrar m?tricas (fail-safe mantido): %s", str(e)[:120])
            return False

    def obter_execucoes(self, filtro_run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """L? todos os registros gravados com filtro opcional de run_id."""
        if not self.log_path.exists():
            return []
        registros = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if filtro_run_id is None or data.get("run_id") == filtro_run_id:
                            registros.append(data)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning("[OBSERVABILIDADE] Erro ao ler hist?rico: %s", str(e)[:120])
        return registros

    def obter_resumo_metricas(self, filtro_run_id: Optional[str] = None) -> Dict[str, Any]:
        """Calcula agrega??es consolidadas sobre os registros operacionais."""
        registros = self.obter_execucoes(filtro_run_id)
        if not registros:
            return {
                "total_registros": 0,
                "documentos_unicos": 0,
                "total_itens": 0,
                "crashes": 0,
                "erros": 0,
                "qualidade": {
                    "fp_generic": 0, "fn_generic": 0, "price_divergence": 0,
                    "unit_divergence": 0, "duplicate": 0, "unresolved": 0, "name_improvement": 0
                },
                "performance": {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0},
            }

        latencias = []
        tot_itens = 0
        crashes = 0
        erros = 0
        hashes_unicos = set()
        qualidade_total = {
            "fp_generic": 0,
            "fn_generic": 0,
            "price_divergence": 0,
            "unit_divergence": 0,
            "duplicate": 0,
            "unresolved": 0,
            "name_improvement": 0,
        }

        for r in registros:
            doc_h = r.get("document_hash")
            if doc_h:
                hashes_unicos.add(doc_h)
            ext = r.get("extraction", {})
            tot_itens += ext.get("itens_validos", 0)
            
            rel = r.get("reliability", {})
            crashes += rel.get("crashes", 0)
            erros += rel.get("exceptions", 0)

            perf = r.get("performance", {})
            lat = perf.get("latencia_extracao_ms")
            if lat is not None:
                latencias.append(float(lat))

            qual = r.get("quality", {})
            for k in qualidade_total:
                qualidade_total[k] += qual.get(k, 0)

        perf_resumo = {
            "p50": percentil(latencias, 50) if latencias else 0.0,
            "p95": percentil(latencias, 95) if latencias else 0.0,
            "p99": percentil(latencias, 99) if latencias else 0.0,
            "max": round(max(latencias), 2) if latencias else 0.0,
        }

        return {
            "total_registros": len(registros),
            "documentos_unicos": len(hashes_unicos),
            "total_itens": tot_itens,
            "crashes": crashes,
            "erros": erros,
            "qualidade": qualidade_total,
            "performance": perf_resumo,
        }

    @staticmethod
    def verificar_integridade_sqlite(
        db_path: Union[str, Path],
        hash_esperado: str = SQLITE_CANONICAL_HASH
    ) -> Dict[str, Any]:
        """Calcula SHA-256 do SQLite e valida estritamente a conformidade com o hash can?nico."""
        p = Path(db_path)
        if not p.exists():
            return {"status": "ARQUIVO_NAO_ENCONTRADO", "valido": False}
        h = calcular_sha256_arquivo(p)
        return {
            "hash": h,
            "esperado": hash_esperado,
            "valido": (h == hash_esperado),
        }
