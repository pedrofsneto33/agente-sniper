# -*- coding: utf-8 -*-
"""
Camada de Armazenamento e Persistência SQLite — Agente Sniper
Responsável por gerenciar schema, transações, persistência de runs, fontes, eventos e snapshots de preços.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from domain.models import Fonte
from domain.identity import sha1


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

        self.conn.commit()

        novos = set()
        alterados = set()
        if prev:
            old = {
                r["fingerprint"]: r["content_hash"]
                for r in self.conn.execute("SELECT fingerprint, content_hash FROM sources WHERE run_id=?", (prev,))
            }
            for f in fontes:
                if f.fingerprint not in old:
                    novos.add(f.fingerprint)
                elif old[f.fingerprint] != sha1(f.conteudo):
                    alterados.add(f.fingerprint)

        return {
            "previous_run": prev,
            "novas_fontes": len(novos),
            "fontes_alteradas": len(alterados)
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
        old_prices: Dict[Tuple[str, str, str], Tuple[Optional[float], bool]] = {}
        if prev:
            for r in self.conn.execute(
                "SELECT entity, source_domain, product_key, price, promotion FROM price_snapshots WHERE run_id=?",
                (prev,)
            ):
                old_prices[(r["entity"], r["source_domain"], r["product_key"])] = (r["price"], bool(r["promotion"]))

        changes: List[Dict[str, Any]] = []
        timestamp = captured_at or datetime.now().isoformat(timespec="seconds")

        for x in snapshots:
            key = (x.get("entity", ""), x.get("source_domain", ""), x.get("product_key", ""))
            old = old_prices.get(key)
            if old and x.get("price") is not None and old[0] not in (None, 0):
                pct = (float(x["price"]) - float(old[0])) / float(old[0]) * 100
                promo_changed = bool(x.get("promotion")) != old[1]
                if abs(pct) >= min_change_pct or promo_changed:
                    changes.append({
                        "entity": x.get("entity"),
                        "source_domain": x.get("source_domain"),
                        "product_key": x.get("product_key"),
                        "product_name": x.get("product_name"),
                        "previous_price": old[0],
                        "current_price": x.get("price"),
                        "change_pct": round(pct, 2),
                        "promotion_before": old[1],
                        "promotion_now": bool(x.get("promotion")),
                        "url": x.get("url", "")
                    })

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

        self.conn.commit()
        return {
            "previous_run": prev,
            "gravados": len(snapshots),
            "mudancas": changes[:100]
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
            out.append(d)
        return out

    def get_price_snapshots(self, run_id: str) -> List[Dict[str, Any]]:
        """Recupera todos os snapshots de preço para uma execução."""
        return [dict(r) for r in self.conn.execute("SELECT * FROM price_snapshots WHERE run_id=?", (run_id,))]

    def close(self) -> None:
        """Encerra a conexão com o banco SQLite."""
        if self.conn:
            self.conn.close()

    def __enter__(self) -> MemoriaSniper:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
