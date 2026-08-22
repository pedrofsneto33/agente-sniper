"""
Testes Unitários do Módulo pipeline.replay (Fase 43B).
Validação de contratos do Replay Offline, integridade de fixtures,
OfflineNetworkGuard isolado e compatibilidade com o orquestrador.
"""

import os
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.replay import (
    OfflineNetworkGuard,
    resolver_fixture_fontes_offline,
    executar_replay_offline,
)
import agente_sniper_v11_8 as sniper

ROOT_DIR = Path(__file__).resolve().parent.parent
CANONICAL_REPLAY_SHA256 = "10a540eb252c3faefe33d72c728961d9cf117edc92d0509e341338092bfce64e"


class TestReplayService(unittest.TestCase):

    def test_01_executar_replay_offline_direto(self):
        """1. Valida execução direta do replay a partir de pipeline.replay."""
        resultado = executar_replay_offline(retornar_detalhes=True, base_dir=ROOT_DIR)
        self.assertIsInstance(resultado, dict)
        self.assertEqual(resultado["retorno"], 0)
        self.assertEqual(resultado["status"], "PASS")
        self.assertEqual(resultado["entidades"], 63)
        self.assertEqual(resultado["eventos"], 34)
        self.assertEqual(resultado["fontes"], 59)
        self.assertEqual(resultado["sha256"], CANONICAL_REPLAY_SHA256)
        self.assertIn("timings_ms", resultado)
        self.assertIn("parsing", resultado["timings_ms"])

    def test_02_resolver_fixture_fontes_offline_com_base_dir_custom(self):
        """2. Valida resolução com base_dir customizado e com override de ambiente."""
        fontes = resolver_fixture_fontes_offline(ROOT_DIR)
        self.assertEqual(len(fontes), 59)

        # Erro quando caminho inválido
        with patch.dict(os.environ, {"OFFLINE_REPLAY_FIXTURE_PATH": "invalido_arquivo_inexistente.json"}):
            with self.assertRaises(FileNotFoundError):
                resolver_fixture_fontes_offline(ROOT_DIR)

    def test_03_offline_network_guard_isolation(self):
        """3. Valida que OfflineNetworkGuard bloqueia qualquer chamada socket.connect."""
        with OfflineNetworkGuard():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                with self.assertRaises(RuntimeError) as ctx:
                    s.connect(("8.8.8.8", 53))
                self.assertIn("[OFFLINE GUARD] Tentativa de conexão de rede BLOQUEADA", str(ctx.exception))

    def test_04_diretorio_ocr_inexistente(self):
        """4. Valida tratamento de erro gracioso quando o diretório de OCR não existe."""
        caminho_falso = ROOT_DIR / "pasta_inexistente_de_ocr"
        res = executar_replay_offline(retornar_detalhes=True, base_dir=caminho_falso)
        self.assertIsInstance(res, dict)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["retorno"], 1)
        self.assertIn("não encontrado", res["erro"])

    def test_05_binding_identity_in_orchestrator(self):
        """5. Valida identidade binária e funcional dos bindings entre o monólito e pipeline.replay."""
        symbols = [
            "OfflineNetworkGuard",
            "resolver_fixture_fontes_offline",
            "executar_replay_offline",
        ]
        import pipeline.replay as pr
        for sym in symbols:
            self.assertTrue(hasattr(sniper, sym), f"Missing {sym} in orchestrator")
            self.assertTrue(hasattr(pr, sym), f"Missing {sym} in pipeline.replay")
            self.assertIs(getattr(sniper, sym), getattr(pr, sym), f"Binding identity failed for {sym}")


if __name__ == "__main__":
    unittest.main()
