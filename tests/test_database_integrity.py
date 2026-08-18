# -*- coding: utf-8 -*-
"""
Testes de Integridade do Banco SQLite — Agente Sniper
Abre sniper_resultados/sniper_historico.sqlite3 em modo somente leitura (URI read-only).
Verifica a existência das tabelas e a contagem de registros sem realizar nenhuma modificação.
"""
import sqlite3
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "sniper_resultados" / "sniper_historico.sqlite3"


class TestDatabaseIntegrity(unittest.TestCase):

    def setUp(self):
        self.assertTrue(DB_PATH.exists(), f"Banco de dados não encontrado em: {DB_PATH}")
        # Conecta usando URI com query string ro=1 (ReadOnly)
        uri = f"file:{DB_PATH.as_posix()}?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True)
        self.cur = self.conn.cursor()

    def tearDown(self):
        self.conn.close()

    def test_01_existencia_de_tabelas_obrigatorias(self):
        """Verifica se todas as tabelas ativas e históricas existem no schema."""
        self.cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tabelas = {row[0] for row in self.cur.fetchall()}

        tabelas_esperadas = {
            "runs",
            "sources",
            "events",
            "price_snapshots",
            "run_meta",
            "price_snapshots_v2",
            "price_matches"
        }
        for t in tabelas_esperadas:
            self.assertIn(t, tabelas, f"Tabela obrigatória ausente no SQLite: {t}")

    def test_02_contagem_de_registros_nao_vazia(self):
        """Confirma que as tabelas possuem registros históricos preservados."""
        self.cur.execute("SELECT COUNT(*) FROM runs")
        runs_count = self.cur.fetchone()[0]
        self.assertGreaterEqual(runs_count, 10, "A tabela 'runs' deve conter pelo menos 10 registros históricos.")

        self.cur.execute("SELECT COUNT(*) FROM sources")
        sources_count = self.cur.fetchone()[0]
        self.assertGreaterEqual(sources_count, 800, "A tabela 'sources' deve conter pelo menos 800 fontes.")

        self.cur.execute("SELECT COUNT(*) FROM events")
        events_count = self.cur.fetchone()[0]
        self.assertGreaterEqual(events_count, 500, "A tabela 'events' deve conter pelo menos 500 eventos.")

        self.cur.execute("SELECT COUNT(*) FROM price_snapshots")
        snapshots_count = self.cur.fetchone()[0]
        self.assertGreaterEqual(snapshots_count, 30, "A tabela 'price_snapshots' deve conter snapshots registrados.")

    def test_03_modo_somente_leitura_impede_escrita(self):
        """Confirma que a conexão de teste é estritamente somente leitura."""
        with self.assertRaises(sqlite3.OperationalError):
            self.cur.execute("CREATE TABLE IF NOT EXISTS test_fail (id INT)")


if __name__ == "__main__":
    unittest.main()
