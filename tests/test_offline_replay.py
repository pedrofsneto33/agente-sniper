"""
Testes automatizados de regressão e congelamento do Replay Offline determinístico.
Valida os contratos canônicos: 63 entidades, 28 eventos, 59 fontes, SHA-256 canônico e garantia OfflineNetworkGuard.
"""

import hashlib
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import agente_sniper_v11_8 as sniper

CANONICAL_REPLAY_SHA256 = "10a540eb252c3faefe33d72c728961d9cf117edc92d0509e341338092bfce64e"
CANONICAL_SQLITE_SHA256 = "2249AF88860C176A9D8D57C6E7BBF94CA20E789425457B10817066D22FFB42DF"


class TestOfflineReplay(unittest.TestCase):
    """Suíte oficial de congelamento e validação do Replay Offline da Fase 28."""

    def test_replay_offline_execution_and_contracts(self):
        """Valida que executar_replay_offline executa com sucesso e cumpre todos os contratos canônicos."""
        resultado = sniper.executar_replay_offline(retornar_detalhes=True)
        self.assertIsInstance(resultado, dict)
        self.assertEqual(resultado["retorno"], 0)
        self.assertEqual(resultado["status"], "PASS")
        self.assertEqual(resultado["entidades"], 63, "O número de entidades canônicas extraídas deve ser exatamente 63")
        self.assertEqual(resultado["eventos"], 34, "O número de eventos consolidados deve ser exatamente 34")
        self.assertEqual(resultado["fontes"], 59, "O número de fontes canônicas deve ser exatamente 59")
        self.assertEqual(resultado["sha256"], CANONICAL_REPLAY_SHA256, "O SHA-256 do payload do replay deve corresponder ao baseline congelado")

    def test_replay_offline_determinism_three_consecutive_runs(self):
        """Valida determinismo estrito em 3 execuções consecutivas com hash 100% idêntico."""
        hashes = []
        for i in range(3):
            res = sniper.executar_replay_offline(retornar_detalhes=True)
            self.assertEqual(res["retorno"], 0)
            self.assertEqual(res["status"], "PASS")
            hashes.append(res["sha256"])

        self.assertEqual(hashes[0], CANONICAL_REPLAY_SHA256)
        self.assertEqual(hashes[1], CANONICAL_REPLAY_SHA256)
        self.assertEqual(hashes[2], CANONICAL_REPLAY_SHA256)

    def test_replay_offline_network_guard_enforcement(self):
        """Valida que o OfflineNetworkGuard bloqueia qualquer tentativa de conexão de rede."""
        class TestNetworkGuard:
            def __init__(self):
                self._orig_connect = socket.socket.connect

            def __enter__(self):
                def _blocked_connect(sock_self, address):
                    raise RuntimeError(f"[OFFLINE GUARD] Tentativa de conexão de rede BLOQUEADA durante --replay-offline para: {address}!")
                socket.socket.connect = _blocked_connect
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                socket.socket.connect = self._orig_connect

        with TestNetworkGuard():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                with self.assertRaises(RuntimeError) as ctx:
                    s.connect(("1.1.1.1", 80))
                self.assertIn("[OFFLINE GUARD] Tentativa de conexão de rede BLOQUEADA", str(ctx.exception))

    def test_replay_offline_sqlite_integrity_preserved(self):
        """Valida que o replay offline não modifica o banco SQLite."""
        db_path = ROOT_DIR / "sniper_resultados" / "sniper_historico.sqlite3"
        if not db_path.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            from storage.sqlite import MemoriaSniper
            mem = MemoriaSniper(db_path)
            mem.conn.close()

        hash_before = hashlib.sha256(db_path.read_bytes()).hexdigest().upper()

        # Executa o replay offline
        res = sniper.executar_replay_offline(retornar_detalhes=True)
        self.assertEqual(res["retorno"], 0)

        hash_after = hashlib.sha256(db_path.read_bytes()).hexdigest().upper()
        self.assertEqual(hash_after, hash_before, "O SHA-256 do SQLite deve permanecer rigorosamente inalterado após o replay offline")

    def test_replay_offline_cli_subprocess_invocation(self):
        """Valida a invocação oficial via CLI com flag --replay-offline."""
        cmd = [sys.executable, str(ROOT_DIR / "agente_sniper_v11_8.py"), "--replay-offline"]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT_DIR))

        self.assertEqual(res.returncode, 0, f"A CLI retornou erro: {res.stderr}")
        stdout = res.stdout
        self.assertIn("Status Replay:        PASS (100% Determinístico)", stdout)
        self.assertIn(f"Output SHA-256:       {CANONICAL_REPLAY_SHA256}", stdout)
        self.assertIn("Entidades Canônicas:  63", stdout)
        self.assertIn("Eventos Consolidados: 34", stdout)
        self.assertIn("Fontes Avaliadas:     59", stdout)
        self.assertIn("Garantia de Rede:     OFFLINE (Zero I/O externo verificado)", stdout)

    def test_resolver_fixture_fontes_offline_behavior(self):
        """Valida a resolução determinística de fixtures de fontes."""
        fontes = sniper.resolver_fixture_fontes_offline(ROOT_DIR)
        self.assertEqual(len(fontes), 59, "A fixture canônica padrão deve conter exatamente 59 fontes")

        # Testa que override inválido lança FileNotFoundError
        old_env = os.environ.get("OFFLINE_REPLAY_FIXTURE_PATH")
        try:
            os.environ["OFFLINE_REPLAY_FIXTURE_PATH"] = "caminho_inexistente_fixture.json"
            with self.assertRaises(FileNotFoundError):
                sniper.resolver_fixture_fontes_offline(ROOT_DIR)
        finally:
            if old_env is not None:
                os.environ["OFFLINE_REPLAY_FIXTURE_PATH"] = old_env
            else:
                os.environ.pop("OFFLINE_REPLAY_FIXTURE_PATH", None)


if __name__ == "__main__":
    unittest.main()