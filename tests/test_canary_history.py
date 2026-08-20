# -*- coding: utf-8 -*-
"""
Bateria de Testes do Histórico Canary e Acúmulo de Evidência — Fase 6E
Valida a persistência append-only em JSONL, deduplicação por hash, resiliência a crashes
e garantia de que SQLite e defaults de produção permanecem 100% inalterados.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from domain.models import PriceItem
from extractors.canary import CanaryDocumentReport
from extractors.canary_history import (
    CanaryHistoryTracker,
    CanaryHistoryRecord,
    calcular_hash_conteudo_ou_arquivo,
)
from agente_sniper_v11_8 import coletar_itens_preco_fonte, EXTRACTION_ENGINE


class TestCanaryHistory(unittest.TestCase):
    """Testa a governança e o acúmulo de evidência do Canary em JSONL."""

    def test_01_primeiro_processamento_adiciona_ao_historico(self):
        """1. Primeiro processamento registra observação válida no JSONL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_path = Path(tmpdir) / "canary_history.jsonl"
            tracker = CanaryHistoryTracker(hist_path)

            doc_rep = CanaryDocumentReport(documento_id="doc1", total_legacy=5, total_generic=5, matches_exatos=5)
            rec = tracker.registrar_observacao(
                run_id="run_01",
                document_id="doc1",
                document_hash="HASH_AAA_111",
                source="Assai",
                doc_report=doc_rep
            )

            self.assertEqual(tracker.total_documentos_unicos(), 1)
            registros = tracker.carregar_registros()
            self.assertEqual(len(registros), 1)
            self.assertEqual(registros[0].document_hash, "HASH_AAA_111")
            self.assertEqual(registros[0].match_exact, 5)

    def test_02_reprocessamento_mesmo_hash_nao_aumenta_n(self):
        """2. Reprocessar o mesmo documento (mesmo hash) não incrementa a contagem de únicos N."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_path = Path(tmpdir) / "canary_history.jsonl"
            tracker = CanaryHistoryTracker(hist_path)

            doc_rep = CanaryDocumentReport(documento_id="doc1", total_legacy=5, total_generic=5)
            tracker.registrar_observacao("run_01", "doc1", "HASH_AAA_111", "Assai", doc_rep)
            tracker.registrar_observacao("run_02", "doc1", "HASH_AAA_111", "Assai", doc_rep)
            tracker.registrar_observacao("run_03", "doc1", "HASH_AAA_111", "Assai", doc_rep)

            self.assertEqual(len(tracker.carregar_registros()), 3)  # 3 linhas gravadas (append-only)
            self.assertEqual(tracker.total_documentos_unicos(), 1)   # N único permanece 1!

    def test_03_documentos_diferentes_aumentam_n(self):
        """3. Documentos com hashes distintos incrementam o total de únicos N."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_path = Path(tmpdir) / "canary_history.jsonl"
            tracker = CanaryHistoryTracker(hist_path)

            doc_rep = CanaryDocumentReport(documento_id="doc", total_legacy=5, total_generic=5)
            tracker.registrar_observacao("run_01", "doc1", "HASH_111", "Assai", doc_rep)
            tracker.registrar_observacao("run_01", "doc2", "HASH_222", "Assai", doc_rep)
            tracker.registrar_observacao("run_01", "doc3", "HASH_333", "Assai", doc_rep)

            self.assertEqual(tracker.total_documentos_unicos(), 3)

    def test_04_jsonl_permanece_valido_linha_a_linha(self):
        """4. Todas as linhas gravadas no JSONL são JSONs estritamente válidos e conformes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_path = Path(tmpdir) / "canary_history.jsonl"
            tracker = CanaryHistoryTracker(hist_path)

            doc_rep = CanaryDocumentReport(documento_id="doc_json", total_legacy=2, total_generic=2)
            tracker.registrar_observacao("run_test", "doc_json", "HASH_JSON", "Assai", doc_rep)

            with open(hist_path, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line.strip())
                    self.assertIn("document_hash", data)
                    self.assertIn("generic_crashed", data)
                    self.assertIsInstance(data["generic_crashed"], bool)

    def test_05_crash_generic_em_shadow_registra_flag_sem_quebrar_legacy(self):
        """5. Falha no Generic em modo Shadow registra generic_crashed=True sem derrubar o Legacy."""
        ocr_path = Path(r"dados_browser/ocr_bruto\49738-102_pagina_1.json")
        if not ocr_path.exists():
            self.skipTest("Fixture real ausente.")

        source = {"name": "Assai", "role": "competitor", "ocr_path": str(ocr_path)}
        old_env = os.environ.get("EXTRACTION_ENGINE")
        os.environ["EXTRACTION_ENGINE"] = "shadow"

        try:
            with patch("extractors.bridge.executar_pipeline_extracao") as mock_bridge:
                def side_effect(origem, engine, **kwargs):
                    if engine == "generic":
                        raise RuntimeError("Simulação de falha no Generic")
                    return {"price_items": [PriceItem("Assai", "competitor", "Item Legacy", "", 15.0)]}
                mock_bridge.side_effect = side_effect

                with tempfile.TemporaryDirectory() as tmpdir:
                    hist_path = Path(tmpdir) / "canary_history.jsonl"
                    with patch("extractors.canary_history.CANARY_HISTORY_PATH", hist_path):
                        items = coletar_itens_preco_fonte(source)
                        self.assertEqual(len(items), 1)
                        self.assertEqual(items[0].name, "Item Legacy")

                        tracker = CanaryHistoryTracker(hist_path)
                        registros = tracker.carregar_registros()
                        self.assertEqual(len(registros), 1)
                        self.assertTrue(registros[0].generic_crashed)
        finally:
            if old_env is not None:
                os.environ["EXTRACTION_ENGINE"] = old_env
            else:
                os.environ.pop("EXTRACTION_ENGINE", None)

    def test_06_sqlite_permanece_intocado(self):
        """6. Garante que CanaryHistoryTracker opera 100% em disco JSONL sem abrir SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_path = Path(tmpdir) / "canary_history.jsonl"
            tracker = CanaryHistoryTracker(hist_path)
            doc_rep = CanaryDocumentReport(documento_id="doc_no_sql", total_legacy=1, total_generic=1)
            tracker.registrar_observacao("run_no_sql", "doc_no_sql", "HASH_NO_SQL", "Assai", doc_rep)
            self.assertTrue(hist_path.exists())
            # Nenhum arquivo .sqlite3 gerado no diretório
            self.assertEqual(len(list(Path(tmpdir).glob("*.sqlite3"))), 0)

    def test_07_default_promovido_generic(self):
        """7. EXTRACTION_ENGINE default no código é promovido para 'generic'."""
        self.assertEqual(EXTRACTION_ENGINE, "generic")


if __name__ == "__main__":
    unittest.main()
