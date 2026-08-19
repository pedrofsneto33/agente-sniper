# -*- coding: utf-8 -*-
"""
Acúmulo de Evidência Operacional em Shadow / Canary — Fase 6E
Persiste registros de observação do Canary de forma append-only em JSONL fora do SQLite,
garantindo deduplicação estrita por document_hash e integridade criptográfica.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from domain.models import PriceItem
from extractors.canary import (
    CanaryDocumentReport,
    comparar_documento_canary,
    percentil,
)


CANARY_HISTORY_PATH = Path(r"C:\Users\User\Desktop\Agente sniper\dados_browser\canary_history.jsonl")


def calcular_hash_conteudo_ou_arquivo(origem: Any) -> str:
    """Calcula hash SHA-256 determinístico de arquivo ou payload JSON/dict."""
    hasher = hashlib.sha256()
    if isinstance(origem, (str, Path)) and Path(origem).exists():
        with open(origem, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
    elif isinstance(origem, (dict, list)):
        payload_bytes = json.dumps(origem, sort_keys=True, ensure_ascii=False).encode("utf-8")
        hasher.update(payload_bytes)
    elif isinstance(origem, str):
        hasher.update(origem.encode("utf-8"))
    else:
        hasher.update(str(origem).encode("utf-8"))
    return hasher.hexdigest().upper()


@dataclass
class CanaryHistoryRecord:
    """Registro imutável de uma observação de documento no histórico Canary."""
    run_id: str
    timestamp: str
    document_id: str
    document_hash: str
    source: str
    legacy_items: int
    generic_items: int
    match_exact: int
    match_semantic: int
    name_improvement: int
    fp_legacy: int
    fn_legacy: int
    fp_generic: int
    fn_generic: int
    price_divergence: int
    unit_divergence: int
    duplicate: int
    unresolved: int
    legacy_latency_ms: float
    generic_latency_ms: float
    generic_crashed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CanaryHistoryTracker:
    """Gerenciador de histórico append-only em JSONL fora do banco de dados SQLite."""

    def __init__(self, history_path: Optional[Path] = None):
        self.history_path = history_path or CANARY_HISTORY_PATH
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def registrar_observacao(
        self,
        run_id: str,
        document_id: str,
        document_hash: str,
        source: str,
        doc_report: CanaryDocumentReport,
        generic_crashed: bool = False,
        timestamp: Optional[str] = None
    ) -> CanaryHistoryRecord:
        """Registra uma nova observação no arquivo JSONL."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        rec = CanaryHistoryRecord(
            run_id=run_id,
            timestamp=ts,
            document_id=document_id,
            document_hash=document_hash,
            source=source,
            legacy_items=doc_report.total_legacy,
            generic_items=doc_report.total_generic,
            match_exact=doc_report.matches_exatos,
            match_semantic=doc_report.matches_semanticos,
            name_improvement=doc_report.melhorias_nome,
            fp_legacy=doc_report.fp_legacy,
            fn_legacy=doc_report.fn_legacy,
            fp_generic=doc_report.fp_generic,
            fn_generic=doc_report.fn_generic,
            price_divergence=doc_report.divergencias_preco,
            unit_divergence=doc_report.divergencias_unidade,
            duplicate=doc_report.duplicatas,
            unresolved=doc_report.unresolved,
            legacy_latency_ms=round(doc_report.tempo_legacy_ms, 2),
            generic_latency_ms=round(doc_report.tempo_generic_ms, 2),
            generic_crashed=generic_crashed
        )

        with open(self.history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")

        return rec

    def carregar_registros(self) -> List[CanaryHistoryRecord]:
        """Carrega todas as linhas do histórico JSONL."""
        if not self.history_path.exists():
            return []
        registros: List[CanaryHistoryRecord] = []
        with open(self.history_path, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    data = json.loads(linha)
                    registros.append(CanaryHistoryRecord(**data))
                except Exception:
                    continue
        return registros

    def obter_documentos_unicos(self) -> Dict[str, CanaryHistoryRecord]:
        """Retorna os registros deduplicados por document_hash (mantendo o mais recente)."""
        todos = self.carregar_registros()
        unicos: Dict[str, CanaryHistoryRecord] = {}
        for r in todos:
            unicos[r.document_hash] = r
        return unicos

    def total_documentos_unicos(self) -> int:
        """Calcula N (quantidade de hashes únicos processados)."""
        return len(self.obter_documentos_unicos())
