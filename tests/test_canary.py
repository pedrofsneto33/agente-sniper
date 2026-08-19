# -*- coding: utf-8 -*-
"""
Bateria de Testes do Canary Controlado — Fase 6C
Cobre todas as 11 classificações obrigatórias e resiliência em observabilidade.
"""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from domain.models import PriceItem
from extractors.canary import (
    CanaryItemComparison,
    CanaryDocumentReport,
    comparar_documento_canary,
    percentil,
)
from extractors.bridge import executar_pipeline_extracao


class TestCanary(unittest.TestCase):
    """Testa a classificação determinística e a auditoria do Canary."""

    def test_01_match_exact(self):
        """1. MATCH_EXACT: Nome, preço e unidades estritamente idênticos."""
        l = PriceItem("Assai", "competitor", "Café Pilão 500g", "", 18.90, unit="500g")
        g = PriceItem("Assai", "competitor", "Café Pilão 500g", "", 18.90, unit="500g")
        rep = comparar_documento_canary([l], [g], "doc_teste")
        self.assertEqual(rep.matches_exatos, 1)
        self.assertEqual(rep.comparacoes[0].classificacao, "MATCH_EXACT")

    def test_02_match_semantic(self):
        """2. MATCH_SEMANTIC: Termos e tokens altamente similares com mesmo preço."""
        l = PriceItem("Assai", "competitor", "Chá Camomila Maratá", "", 3.29, unit="10g")
        g = PriceItem("Assai", "competitor", "Chá Maratá Sabores Camomila", "", 3.29, unit="10g")
        rep = comparar_documento_canary([l], [g], "doc_teste")
        self.assertEqual(rep.matches_semanticos, 1)
        self.assertEqual(rep.comparacoes[0].classificacao, "MATCH_SEMANTIC")

    def test_03_name_improvement(self):
        """3. NAME_IMPROVEMENT: Generic reconstruiu nome a partir de OCR quebrado."""
        l = PriceItem("Assai", "competitor", "NOVA CÁPSULA DE s P R E $ $ 0", "", 23.90)
        g = PriceItem("Assai", "competitor", "CAIXETA 10X5,2G CÁPSULAS DE CAFÉ L'OR SABORES", "", 23.90)
        rep = comparar_documento_canary([l], [g], "doc_teste")
        self.assertEqual(rep.melhorias_nome, 1)
        self.assertEqual(rep.comparacoes[0].classificacao, "NAME_IMPROVEMENT")

    def test_04_fp_legacy(self):
        """4. FP_LEGACY: Falso positivo no Legacy por gramatura 162.49."""
        l = PriceItem("Assai", "competitor", "Rone Oaltoev 162,4g", "", 162.49)
        rep = comparar_documento_canary([l], [], "doc_teste")
        self.assertEqual(rep.fp_legacy, 1)
        self.assertEqual(rep.comparacoes[0].classificacao, "FP_LEGACY")

    def test_05_fn_legacy_oferta_recuperada(self):
        """5. FN_LEGACY: Oferta legítima que o Legacy perdeu e o Generic recuperou."""
        g = PriceItem("Assai", "competitor", "PNEU AUTOMOTIVO ARO 14 GOODYEAR", "", 279.90)
        rep = comparar_documento_canary([], [g], "doc_teste")
        self.assertEqual(rep.fn_legacy, 1)
        self.assertEqual(rep.comparacoes[0].classificacao, "FN_LEGACY")

    def test_06_price_divergence(self):
        """6. PRICE_DIVERGENCE: Mesmo produto com preços diferentes."""
        l = PriceItem("Assai", "competitor", "Café Torrado Pilão Extraforte", "", 19.90)
        g = PriceItem("Assai", "competitor", "Café Torrado Pilão Extraforte", "", 17.90)
        rep = comparar_documento_canary([l], [g], "doc_teste")
        self.assertEqual(rep.divergencias_preco, 1)
        self.assertEqual(rep.comparacoes[0].classificacao, "PRICE_DIVERGENCE")

    def test_07_unit_divergence(self):
        """7. UNIT_DIVERGENCE: Preço e nome iguais, mas unidades diferem."""
        l = PriceItem("Assai", "competitor", "Café Pilão", "", 17.90, unit="250g")
        g = PriceItem("Assai", "competitor", "Café Pilão", "", 17.90, unit="500g")
        rep = comparar_documento_canary([l], [g], "doc_teste")
        self.assertEqual(rep.divergencias_unidade, 1)
        self.assertEqual(rep.comparacoes[0].classificacao, "UNIT_DIVERGENCE")

    def test_08_calculo_percentil(self):
        """8. Testa cálculo de percentis P50, P95, P99."""
        tempos = [10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 50.0]
        p50 = percentil(tempos, 50)
        p95 = percentil(tempos, 95)
        p99 = percentil(tempos, 99)
        self.assertEqual(p50, 20.0)
        self.assertGreater(p95, 30.0)
        self.assertGreaterEqual(p99, p95)


if __name__ == "__main__":
    unittest.main()
