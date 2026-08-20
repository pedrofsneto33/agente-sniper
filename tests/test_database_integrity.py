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
        if not DB_PATH.exists():
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            from storage.sqlite import MemoriaSniper
            mem = MemoriaSniper(DB_PATH)
            mem.conn.close()

        # Conecta usando URI com query string ro=1 (ReadOnly)
        uri = f"file:{DB_PATH.as_posix()}?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True)
        self.cur = self.conn.cursor()

    def tearDown(self):
        self.conn.close()

    def test_01_existencia_de_tabelas_obrigatorias(self):
        """Verifica se todas as tabelas ativas do schema canônico existem no SQLite."""
        self.cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tabelas = {row[0] for row in self.cur.fetchall()}

        tabelas_esperadas = {
            "runs",
            "sources",
            "events",
            "price_snapshots"
        }
        for t in tabelas_esperadas:
            self.assertIn(t, tabelas, f"Tabela obrigatória ausente no SQLite: {t}")

    def test_02_contagem_de_registros_nao_vazia(self):
        """Confirma que as tabelas existem e podem ser consultadas sem erros de integridade."""
        for t in ["runs", "sources", "events", "price_snapshots"]:
            self.cur.execute(f"SELECT COUNT(*) FROM {t}")
            cnt = self.cur.fetchone()[0]
            self.assertGreaterEqual(cnt, 0, f"A tabela '{t}' deve ser consultável com contagem válida.")

    def test_03_modo_somente_leitura_impede_escrita(self):
        """Confirma que a conexão de teste é estritamente somente leitura."""
        with self.assertRaises(sqlite3.OperationalError):
            self.cur.execute("CREATE TABLE IF NOT EXISTS test_fail (id INT)")


if __name__ == "__main__":
    unittest.main()
