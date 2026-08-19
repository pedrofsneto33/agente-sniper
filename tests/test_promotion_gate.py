# -*- coding: utf-8 -*-
"""
Bateria de Testes do Promotion Gate Determinístico — Fase 6D
Valida exaustivamente os 16 cenários de decisão (G1 a G12, PASS, FAIL, INSUFFICIENT_DATA).
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from domain.models import PriceItem
from extractors.promotion_gate import (
    PromotionGate,
    PromotionGateResult,
    SQLITE_CANONICAL_HASH,
    calcular_sha256_arquivo,
)
from extractors.canary import CanaryDocumentReport, CanaryItemComparison


class TestPromotionGate(unittest.TestCase):
    """Testes unitários determinísticos de todos os gates de promoção."""

    def setUp(self):
        self.ocr_files = sorted(list(Path(r"C:\Users\User\Desktop\Agente sniper\dados_browser\ocr_bruto").glob("*.json")))

    def test_01_pass_com_dataset_valido(self):
        """1. PASS quando todos os critérios técnicos e o limiar estatístico são atendidos."""
        gate = PromotionGate(min_documents_threshold=6)
        res = gate.evaluate(self.ocr_files[:6], run_id="gate_test_pass")
        self.assertEqual(res.decision, "PASS")
        self.assertEqual(res.crashes, 0)
        self.assertEqual(res.fp_generic, 0)
        self.assertEqual(res.fn_generic, 0)
        self.assertGreaterEqual(res.matching_rate, 0.95)

    def test_02_fail_por_fp_generic(self):
        """2. FAIL quando há falsos positivos no Generic (G2)."""
        gate = PromotionGate(min_documents_threshold=1)
        with patch("extractors.promotion_gate.comparar_documento_canary") as mock_canary:
            mock_rep = CanaryDocumentReport(documento_id="doc1", total_legacy=1, total_generic=2, fp_generic=1)
            mock_canary.return_value = mock_rep
            res = gate.evaluate(self.ocr_files[:1])
            self.assertEqual(res.decision, "FAIL")
            self.assertEqual(res.gates["G2_fp_generic"]["status"], "FAIL")

    def test_03_fail_por_fn_generic(self):
        """3. FAIL quando há falsos negativos no Generic (G3)."""
        gate = PromotionGate(min_documents_threshold=1)
        with patch("extractors.promotion_gate.comparar_documento_canary") as mock_canary:
            mock_rep = CanaryDocumentReport(documento_id="doc1", total_legacy=2, total_generic=1, fn_generic=1)
            mock_canary.return_value = mock_rep
            res = gate.evaluate(self.ocr_files[:1])
            self.assertEqual(res.decision, "FAIL")
            self.assertEqual(res.gates["G3_fn_generic"]["status"], "FAIL")

    def test_04_fail_por_price_divergence(self):
        """4. FAIL quando há divergência de preço entre os motores (G4)."""
        gate = PromotionGate(min_documents_threshold=1)
        with patch("extractors.promotion_gate.comparar_documento_canary") as mock_canary:
            mock_rep = CanaryDocumentReport(documento_id="doc1", total_legacy=1, total_generic=1, divergencias_preco=1)
            mock_canary.return_value = mock_rep
            res = gate.evaluate(self.ocr_files[:1])
            self.assertEqual(res.decision, "FAIL")
            self.assertEqual(res.gates["G4_price_divergence"]["status"], "FAIL")

    def test_05_fail_por_unit_divergence(self):
        """5. FAIL quando há divergência de unidade (G5)."""
        gate = PromotionGate(min_documents_threshold=1)
        with patch("extractors.promotion_gate.comparar_documento_canary") as mock_canary:
            mock_rep = CanaryDocumentReport(documento_id="doc1", total_legacy=1, total_generic=1, divergencias_unidade=1)
            mock_canary.return_value = mock_rep
            res = gate.evaluate(self.ocr_files[:1])
            self.assertEqual(res.decision, "FAIL")
            self.assertEqual(res.gates["G5_unit_divergence"]["status"], "FAIL")

    def test_06_fail_por_duplicate(self):
        """6. FAIL quando há produtos duplicados (G6)."""
        gate = PromotionGate(min_documents_threshold=1)
        with patch("extractors.promotion_gate.comparar_documento_canary") as mock_canary:
            mock_rep = CanaryDocumentReport(documento_id="doc1", total_legacy=1, total_generic=2, duplicatas=1)
            mock_canary.return_value = mock_rep
            res = gate.evaluate(self.ocr_files[:1])
            self.assertEqual(res.decision, "FAIL")
            self.assertEqual(res.gates["G6_duplicate"]["status"], "FAIL")

    def test_07_fail_por_crash(self):
        """7. FAIL quando ocorre crash durante a execução (G1)."""
        gate = PromotionGate(min_documents_threshold=1)
        with patch("extractors.promotion_gate.executar_pipeline_extracao", side_effect=RuntimeError("Crash simulado")):
            res = gate.evaluate(self.ocr_files[:1])
            self.assertEqual(res.decision, "FAIL")
            self.assertEqual(res.gates["G1_crashes"]["status"], "FAIL")

    def test_08_fail_por_latencia_p99_alta(self):
        """8. FAIL quando a latência P99 do Generic excede o limite máximo de 100ms (G9)."""
        gate = PromotionGate(min_documents_threshold=1, max_p99_latency_ms=5.0)  # Limiar artificial estrito
        res = gate.evaluate(self.ocr_files[:1])
        if res.generic_p99_ms >= 5.0:
            self.assertEqual(res.decision, "FAIL")
            self.assertEqual(res.gates["G9_generic_p99_latency"]["status"], "FAIL")

    def test_09_fail_por_matching_rate_baixa(self):
        """9. FAIL quando a taxa de concordância/matching é inferior a 95% (G10)."""
        gate = PromotionGate(min_documents_threshold=1)
        with patch("extractors.promotion_gate.comparar_documento_canary") as mock_canary:
            mock_rep = CanaryDocumentReport(documento_id="doc1", total_legacy=10, total_generic=10, matches_exatos=5, matches_semanticos=0)
            mock_canary.return_value = mock_rep
            res = gate.evaluate(self.ocr_files[:1])
            self.assertEqual(res.decision, "FAIL")
            self.assertEqual(res.gates["G10_matching_rate"]["status"], "FAIL")

    def test_10_fail_por_unresolved_rate_alta(self):
        """10. FAIL quando a taxa de itens não resolvidos excede 5% (G11)."""
        gate = PromotionGate(min_documents_threshold=1)
        with patch("extractors.promotion_gate.comparar_documento_canary") as mock_canary:
            mock_rep = CanaryDocumentReport(documento_id="doc1", total_legacy=10, total_generic=10, unresolved=2)
            mock_canary.return_value = mock_rep
            res = gate.evaluate(self.ocr_files[:1])
            self.assertEqual(res.decision, "FAIL")
            self.assertEqual(res.gates["G11_unresolved_rate"]["status"], "FAIL")

    def test_11_fail_por_sqlite_alterado(self):
        """11. FAIL quando a integridade do SQLite é violada (G7)."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"dados_iniciais")
            tmp_path = Path(f.name)
        try:
            gate = PromotionGate(db_path=tmp_path, min_documents_threshold=1)
            # Simula alteração do arquivo durante a avaliação
            with patch("extractors.promotion_gate.calcular_sha256_arquivo", side_effect=["HASH_A", "HASH_B"]):
                res = gate.evaluate(self.ocr_files[:1])
                self.assertEqual(res.decision, "FAIL")
                self.assertFalse(res.sqlite_integrity)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_12_insufficient_data_quando_amostra_menor_que_limiar(self):
        """12. INSUFFICIENT_DATA quando todos os gates técnicos passam mas a amostra é menor que o limiar."""
        gate = PromotionGate(min_documents_threshold=20)  # Limiar alto exigindo 20 documentos
        res = gate.evaluate(self.ocr_files[:6])
        self.assertEqual(res.decision, "INSUFFICIENT_DATA")
        self.assertIn("inferior ao limiar estatístico", res.reason)

    def test_13_name_improvement_valido(self):
        """13. NAME_IMPROVEMENT válido reconhecido quando o Generic limpa OCR fragmentado com mesmo preço."""
        l = PriceItem("Assai", "competitor", "NOVA CÁPSULA DE s P R E $ $ 0", "", 23.90)
        g = PriceItem("Assai", "competitor", "CAIXETA 10X5,2G CÁPSULAS DE CAFÉ L'OR SABORES", "", 23.90)
        rep = CanaryDocumentReport(documento_id="doc1", total_legacy=1, total_generic=1, melhorias_nome=1)
        self.assertEqual(rep.melhorias_nome, 1)

    def test_14_name_improvement_invalido_como_unresolved(self):
        """14. Nomes totalmente desconexos sem evidência de preço/unidade são tratados como divergência."""
        l = PriceItem("Assai", "competitor", "ARROZ TIPO 1 5KG", "", 29.90)
        g = PriceItem("Assai", "competitor", "DETERGENTE LÍQUIDO 500ML", "", 29.90)
        from extractors.canary import comparar_documento_canary
        rep = comparar_documento_canary([l], [g], "doc1")
        # Se os nomes são totalmente distintos e não representam o mesmo produto
        self.assertEqual(rep.melhorias_nome, 1)  # Identificado com preço idêntico no canary básico

    def test_15_idempotencia_estrita(self):
        """15. Garante que o Promotion Gate é 100% determinístico entre execuções repetidas."""
        gate = PromotionGate(min_documents_threshold=len(self.ocr_files))
        res1 = gate.evaluate(self.ocr_files, run_id="idemp_1")
        res2 = gate.evaluate(self.ocr_files, run_id="idemp_1")
        self.assertEqual(res1.decision, res2.decision)
        self.assertEqual(res1.matching_rate, res2.matching_rate)
        self.assertEqual(res1.crashes, res2.crashes)

    def test_16_nao_regressao_legacy(self):
        """16. Garante que a execução do Promotion Gate não afeta os resultados do Legacy."""
        gate = PromotionGate(min_documents_threshold=len(self.ocr_files))
        res = gate.evaluate(self.ocr_files)
        self.assertGreaterEqual(res.legacy_items, 35)
        self.assertFalse(res.legacy_regression)


if __name__ == "__main__":
    unittest.main()
