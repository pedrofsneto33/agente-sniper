# -*- coding: utf-8 -*-
"""
Testes Unit?rios de Robustez do Parser de Moeda e Pre?os ? Fase Cir?rgica
Garante suporte ao formato de milhar brasileiro (ex: R$ 1.250,00) sem falsos positivos em gramaturas.
"""

import unittest
from extractors.candidates import StrictCurrencyRule
from extractors.models import SpatialToken, RawSpatialDocument, BoundingBox


class TestCurrencyParser(unittest.TestCase):
    """Testa as regras de extra??o monet?ria da StrictCurrencyRule."""

    def setUp(self):
        self.rule = StrictCurrencyRule()

    def _detect(self, text: str):
        tok = SpatialToken(
            id_token="t1",
            texto=text,
            bbox=BoundingBox(100, 100, 200, 150),
            confianca=0.95
        )
        doc = RawSpatialDocument(
            identificador="doc_test",
            origem="test",
            tokens=[tok]
        )
        return self.rule.detect([tok], doc)

    def test_01_milhar_com_cifrao(self):
        """1. Testa formatos de milhar com s?mbolo R$."""
        casos = [
            ("R$ 1.250,00", 1250.00),
            ("R$ 1.999,99", 1999.99),
            ("R$ 10.000,00", 10000.00),
            ("R$ 125.000,00", 125000.00),
        ]
        for txt, expected in casos:
            res = self._detect(txt)
            self.assertEqual(len(res), 1, f"Falha na detec??o de {txt}")
            self.assertEqual(res[0].valor_normalizado, expected)

    def test_02_milhar_sem_cifrao(self):
        """2. Testa formatos de milhar sem s?mbolo R$."""
        casos = [
            ("1.250,00", 1250.00),
            ("12.500,00", 12500.00),
            ("125.000,00", 125000.00),
        ]
        for txt, expected in casos:
            res = self._detect(txt)
            self.assertEqual(len(res), 1, f"Falha na detec??o de {txt}")
            self.assertEqual(res[0].valor_normalizado, expected)

    def test_03_precos_padrao_existentes(self):
        """3. Preserva todos os formatos padr?o j? suportados."""
        casos = [
            ("R$ 999,99", 999.99),
            ("R$ 279,90", 279.90),
            ("279,90", 279.90),
            ("279.90", 279.90),
            ("R$ 0,15", 0.15),
        ]
        for txt, expected in casos:
            res = self._detect(txt)
            self.assertEqual(len(res), 1, f"Falha na detec??o de {txt}")
            self.assertEqual(res[0].valor_normalizado, expected)

    def test_04_rejeicao_estrita_nao_moeda(self):
        """4. Garante que gramaturas, volumes e identificadores n?o viram pre?o."""
        nao_precos = [
            "162,4g",
            "1,6KG",
            "10x5,2g",
            "500g",
            "10%",
            "20/12/2026",
            "7891000315507",
        ]
        for txt in nao_precos:
            res = self._detect(txt)
            self.assertEqual(len(res), 0, f"Falso positivo gerado para {txt}: {res}")


if __name__ == "__main__":
    unittest.main()
