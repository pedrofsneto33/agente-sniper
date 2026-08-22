# -*- coding: utf-8 -*-
"""
Camada de Armazenamento e Persistência SQLite — Agente Sniper
Responsável por gerenciar schema, transações, persistência de runs, fontes, eventos e snapshots de preços.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from domain.models import Fonte
from domain.identity import sha1
from domain.normalizer import parse_data
from domain.events import EVENT_CONTEXTUAL_MAX_DAYS
from domain.deltas import calcular_delta_fontes, calcular_delta_eventos
from domain.pricing import detectar_mudancas_preco, calcular_serie_temporal_precos


class MemoriaSniper:
    """Gerenciador de persistência histórica em banco SQLite local."""

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self._schema()

    def _schema(self) -> None:
        """Cria e valida o schema canônico do SQLite histórico."""
        c = self.conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            empresa TEXT,
            nicho TEXT,
            cidade TEXT,
            estado TEXT,
            created_at TEXT
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            run_id TEXT,
            fingerprint TEXT,
            url TEXT,
            title TEXT,
            category TEXT,
            score REAL,
            current INTEGER,
            content_hash TEXT,
            PRIMARY KEY (run_id, fingerprint)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            run_id TEXT,
            event_key TEXT,
            kind TEXT,
            title TEXT,
            importance INTEGER,
            evidence_ids TEXT,
            created_at TEXT,
            PRIMARY KEY (run_id, event_key)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS price_snapshots (
            run_id TEXT, entity TEXT, role TEXT, source_domain TEXT, product_key TEXT,
            product_name TEXT, brand TEXT, unit TEXT, price REAL, old_price REAL, promotion INTEGER,
            url TEXT, location_note TEXT, captured_at TEXT,
            PRIMARY KEY (run_id, entity, source_domain, product_key)
        )""")
        self.conn.commit()

    def previous_run(self) -> Optional[str]:
        """Recupera o identificador da execução anterior mais recente."""
        r = self.conn.execute("SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
        return str(r[0]) if r else None

    def save_run(
        self,
        run_id: str,
        fontes: Sequence[Fonte],
        events: Sequence[Dict[str, Any]],
        empresa: str = "",
        nicho: str = "",
        cidade: str = "",
        estado: str = "",
        created_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """Persiste metadados da run, fontes coletadas, eventos detectados e calcula deltas."""
        prev = self.previous_run()
        timestamp = created_at or datetime.now().isoformat(timespec="seconds")
        ref_dt = parse_data(timestamp[:19]) if timestamp else None

        # Recupera eventos históricos cobrindo o horizonte contextual (180 dias)
        historico_eventos: List[Dict[str, Any]] = []
        if prev:
            since_date: Optional[str] = None
            if ref_dt:
                since_date = (ref_dt - timedelta(days=EVENT_CONTEXTUAL_MAX_DAYS)).strftime("%Y-%m-%d")
            historico_eventos = self.get_event_history(since=since_date, limit_runs=None)

        try:
            with self.conn:
                self.conn.execute(
                    "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)",
                    (run_id, empresa, nicho, cidade, estado, timestamp)
                )

                for f in fontes:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?)",
                        (run_id, f.fingerprint, f.url, f.titulo, f.categoria, f.score, int(f.atual), sha1(f.conteudo))
                    )

                for e in events:
                    # Contrato canônico: eventos usam event_id.
                    # event_key é aceito como compatibilidade com versões antigas.
                    event_key = e.get("event_id") or e.get("event_key")
                    if not event_key:
                        raise ValueError(
                            "Evento inválido: ausência de event_id/event_key. "
                            f"kind={e.get('kind')!r}, title={e.get('title')!r}"
                        )
                    kind = str(e.get("kind") or "MOVIMENTO")
                    title = str(e.get("title") or "Evento sem título")
                    importance = int(float(e.get("importance", 0)))
                    evidence_ids = [int(x) for x in (e.get("evidence_ids") or []) if str(x).isdigit()]
                    self.conn.execute(
                        "INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?)",
                        (run_id, event_key, kind, title, importance, json.dumps(evidence_ids), timestamp)
                    )
        except Exception:
            self.conn.rollback()
            raise

        old_hashes: Optional[Dict[str, str]] = None
        if prev:
            old_hashes = {
                r["fingerprint"]: r["content_hash"]
                for r in self.conn.execute("SELECT fingerprint, content_hash FROM sources WHERE run_id=?", (prev,))
            }

        delta_fontes = calcular_delta_fontes(fontes, old_hashes)
        eventos_delta = calcular_delta_eventos(events, historico_eventos, hoje=ref_dt)

        return {
            "previous_run": prev,
            "novas_fontes": delta_fontes["novas_fontes"],
            "fontes_alteradas": delta_fontes["fontes_alteradas"],
            "eventos_delta": eventos_delta,
        }

    def save_price_snapshots(
        self,
        run_id: str,
        snapshots: Sequence[Dict[str, Any]],
        captured_at: Optional[str] = None,
        min_change_pct: float = 0.5
    ) -> Dict[str, Any]:
        """Persiste snapshots de preços e rastreia variações percentuais/promocionais."""
        prev = self.previous_run()
        old_prices: Optional[Dict[Tuple[str, str, str], Tuple[Optional[float], bool]]] = None
        if prev:
            old_prices = {}
            for r in self.conn.execute(
                "SELECT entity, source_domain, product_key, price, promotion FROM price_snapshots WHERE run_id=?",
                (prev,)
            ):
                old_prices[(r["entity"], r["source_domain"], r["product_key"])] = (r["price"], bool(r["promotion"]))

        changes = detectar_mudancas_preco(snapshots, old_prices, min_change_pct=min_change_pct)
        timestamp = captured_at or datetime.now().isoformat(timespec="seconds")

        try:
            with self.conn:
                for x in snapshots:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO price_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            run_id,
                            x.get("entity", ""),
                            x.get("role", ""),
                            x.get("source_domain", ""),
                            x.get("product_key", ""),
                            x.get("product_name", ""),
                            x.get("brand", ""),
                            x.get("unit", ""),
                            x.get("price"),
                            x.get("old_price"),
                            int(bool(x.get("promotion"))),
                            x.get("url", ""),
                            x.get("location_note", ""),
                            timestamp
                        )
                    )
        except Exception:
            self.conn.rollback()
            raise
        return {
            "previous_run": prev,
            "gravados": len(snapshots),
            "mudancas": changes
        }

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Recupera os metadados de uma execução por ID."""
        r = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    def get_sources(self, run_id: str) -> List[Dict[str, Any]]:
        """Recupera todas as fontes persistidas para uma execução."""
        return [dict(r) for r in self.conn.execute("SELECT * FROM sources WHERE run_id=?", (run_id,))]

    def get_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Recupera todos os eventos persistidos para uma execução."""
        out = []
        for r in self.conn.execute("SELECT * FROM events WHERE run_id=?", (run_id,)):
            d = dict(r)
            if "evidence_ids" in d and isinstance(d["evidence_ids"], str):
                try:
                    d["evidence_ids"] = json.loads(d["evidence_ids"])
                except Exception:
                    pass
            if "created_at" in d and "date" not in d and d["created_at"]:
                d["date"] = d["created_at"][:10]
            if "event_key" in d and "event_id" not in d:
                d["event_id"] = d["event_key"]
            out.append(d)
        return out

    def get_event_history(
        self,
        limit_runs: Optional[int] = None,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Recupera eventos persistidos em múltiplas execuções com ordenação determinística.

        :param limit_runs: Quantidade de execuções anteriores a considerar (None ou <=0 para todas).
        :param since: Filtro opcional de data mínima ISO (ex: "2026-08-01").
        :return: Lista de dicionários de eventos com evidence_ids deserializados.
        """
        query_runs = "SELECT run_id FROM runs"
        params_runs: List[Any] = []
        if since:
            query_runs += " WHERE created_at >= ?"
            params_runs.append(since)
        query_runs += " ORDER BY created_at DESC"
        if limit_runs is not None and limit_runs > 0:
            query_runs += " LIMIT ?"
            params_runs.append(limit_runs)

        target_runs = [r[0] for r in self.conn.execute(query_runs, params_runs).fetchall()]
        if not target_runs:
            return []

        placeholders = ",".join("?" for _ in target_runs)
        sql = f"""
            SELECT * FROM events
            WHERE run_id IN ({placeholders})
            ORDER BY created_at ASC, event_key ASC, run_id ASC
        """
        out: List[Dict[str, Any]] = []
        for r in self.conn.execute(sql, target_runs):
            d = dict(r)
            if "evidence_ids" in d and isinstance(d["evidence_ids"], str):
                try:
                    d["evidence_ids"] = json.loads(d["evidence_ids"])
                except Exception:
                    pass
            if "created_at" in d and "date" not in d and d["created_at"]:
                d["date"] = d["created_at"][:10]
            if "event_key" in d and "event_id" not in d:
                d["event_id"] = d["event_key"]
            out.append(d)
        return out

    def get_price_snapshots(self, run_id: str) -> List[Dict[str, Any]]:
        """Recupera todos os snapshots de preço para uma execução."""
        return [dict(r) for r in self.conn.execute("SELECT * FROM price_snapshots WHERE run_id=?", (run_id,))]

    def get_all_price_snapshots(
        self,
        limit_runs: Optional[int] = None,
        since: Optional[str] = None,
        entity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Recupera snapshots de preço consolidados de múltiplas runs em ordem cronológica determinística.

        :param limit_runs: Quantidade de execuções anteriores a considerar (None ou <=0 para todas).
        :param since: Filtro opcional de data mínima ISO de captura (price_snapshots.captured_at >= since).
        :param entity: Filtro opcional por nome da entidade.
        :return: Lista de dicionários de snapshots ordenados por captured_at ASC e desempate por run_id ASC.
        """
        conditions: List[str] = []
        params_snaps: List[Any] = []

        if limit_runs is not None and limit_runs > 0:
            query_runs = "SELECT run_id FROM runs ORDER BY created_at DESC LIMIT ?"
            target_runs = [r[0] for r in self.conn.execute(query_runs, (limit_runs,)).fetchall()]
            if not target_runs:
                return []
            placeholders = ",".join("?" for _ in target_runs)
            conditions.append(f"run_id IN ({placeholders})")
            params_snaps.extend(target_runs)

        if since:
            conditions.append("captured_at >= ?")
            params_snaps.append(since)

        if entity:
            conditions.append("entity = ?")
            params_snaps.append(entity)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT * FROM price_snapshots
            {where_clause}
            ORDER BY captured_at ASC, entity ASC, source_domain ASC, product_key ASC, run_id ASC
        """
        return [dict(r) for r in self.conn.execute(sql, params_snaps)]

    def get_price_series(
        self,
        entity: Optional[str] = None,
        limit_runs: Optional[int] = None,
        since: Optional[str] = None,
        janelas_dias: Sequence[int] = (7, 15, 30),
        hoje: Optional[datetime] = None
    ) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
        """
        Recupera snapshots históricos e calcula séries temporais delegando ao domínio puro.

        :param entity: Filtro opcional por entidade.
        :param limit_runs: Limite opcional de execuções históricas.
        :param since: Filtro opcional de data inicial.
        :param janelas_dias: Janelas em dias para cálculo de variações temporais.
        :param hoje: Ponto temporal de referência opcional.
        :return: Mapeamento {(entity, source_domain, product_key): resumo_serie}.
        """
        snaps = self.get_all_price_snapshots(limit_runs=limit_runs, since=since, entity=entity)
        return calcular_serie_temporal_precos(snaps, janelas_dias=janelas_dias, hoje=hoje)

    def close(self) -> None:
        """Encerra a conexão com o banco SQLite."""
        if self.conn:
            self.conn.close()

    def __enter__(self) -> MemoriaSniper:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
