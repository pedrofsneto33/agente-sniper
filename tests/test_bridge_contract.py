# -*- coding: utf-8 -*-
"""
Testes de Contrato e Integração da Ponte (Bridge) — Fase 4
Garante integridade da Feature Flag e compatibilidade com o pipeline de produção.
"""

import os
import unittest
from pathlib import Path

from extractors.bridge import (
    obter_engine_ativo,
    carregar_ocr_bruto,
    converter_entidades_para_price_items,
    converter_para_schema_legacy_cards,
    executar_pipeline_extracao,
)
from extractors.models import RawSpatialDocument, ExtractedEntity, BoundingBox
from domain.models import PriceItem


class TestBridgeContract(unittest.TestCase):
    """Testa os contratos de entrada, saída e compatibilidade da ponte."""

    def test_01_feature_flag_padrao_eh_generic(self):
        """Garante que o motor padrão operacional promovido sem variável de ambiente é 'generic'."""
        old_val = os.environ.pop("EXTRACTION_ENGINE", None)
        try:
            self.assertEqual(obter_engine_ativo(), "generic")
        finally:
            if old_val is not None:
                os.environ["EXTRACTION_ENGINE"] = old_val

    def test_02_conversao_entidade_para_price_item(self):
        """Garante que ExtractedEntity é convertida fielmente no modelo PriceItem de domínio."""
        ent = ExtractedEntity(
            entidade="produto",
            atributos={"nome": "Café Pilão", "peso_volume": "500g"},
            valor=18.90,
            unidade="BRL",
            confianca=0.95
        )
        items = converter_entidades_para_price_items([ent], source="Assai", role="competitor")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertIsInstance(item, PriceItem)
        self.assertEqual(item.name, "Café Pilão")
        self.assertEqual(item.price, 18.90)
        self.assertEqual(item.unit, "500g")
        self.assertEqual(item.source, "Assai")
        self.assertEqual(item.role, "competitor")

    def test_03_execucao_bridge_generic_vs_legacy_em_fixture_real(self):
        """Compara a execução da ponte nos modos legacy e generic sobre 49738-102_pagina_1.json."""
        caminho_ocr = Path(r"C:\Users\User\Desktop\Agente sniper\dados_browser\ocr_bruto\49738-102_pagina_1.json")
        if not caminho_ocr.exists():
            self.skipTest("Fixture real não encontrada.")

        # 1. Execução no modo LEGACY
        res_legacy = executar_pipeline_extracao(caminho_ocr, engine="legacy")
        self.assertEqual(res_legacy["engine"], "legacy")
        self.assertEqual(res_legacy["documento_id"], "49738-102_pagina_1")
        self.assertGreater(len(res_legacy["price_items"]), 0)

        # 2. Execução no modo GENERIC
        res_generic = executar_pipeline_extracao(caminho_ocr, engine="generic")
        self.assertEqual(res_generic["engine"], "generic")
        self.assertEqual(res_generic["documento_id"], "49738-102_pagina_1")
        self.assertEqual(len(res_generic["price_items"]), 7)

        # O modo generic deve ter suprimido o falso preço de 162.40 (162,4g)
        precos_generic = [p.price for p in res_generic["price_items"]]
        self.assertNotIn(162.40, precos_generic)

    def test_04_adapter_compatibilidade_reversa_cards(self):
        """Valida que converter_para_schema_legacy_cards produz o formato compatível com cards_candidatos_v2."""
        caminho_ocr = Path(r"C:\Users\User\Desktop\Agente sniper\dados_browser\ocr_bruto\49738-102_pagina_1.json")
        if not caminho_ocr.exists():
            self.skipTest("Fixture real não encontrada.")

        res_generic = executar_pipeline_extracao(caminho_ocr, engine="generic")
        schema_cards = converter_para_schema_legacy_cards(res_generic["resultado_canonico"])

        self.assertIn("arquivo", schema_cards)
        self.assertIn("total_cards", schema_cards)
        self.assertIn("cards", schema_cards)
        self.assertEqual(len(schema_cards["cards"]), 7)
        self.assertIn("preco", schema_cards["cards"][0])
        self.assertIn("textos", schema_cards["cards"][0])


if __name__ == "__main__":
    unittest.main()
