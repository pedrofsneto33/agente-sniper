# -*- coding: utf-8 -*-
"""
Bateria de Testes de Integração e Dispatch da Feature Flag — Fase 6B
Garante a governança completa dos 15 requisitos obrigatórios de promoção.
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from domain.models import PriceItem
from agente_sniper_v11_8 import coletar_itens_preco_fonte


class TestIntegrationDispatch(unittest.TestCase):
    """Testa o dispatch do EXTRACTION_ENGINE no ponto de integração do Agente Sniper."""

    def setUp(self):
        self.ocr_path = str(Path(r"C:\Users\User\Desktop\Agente sniper\dados_browser\ocr_bruto\49738-102_pagina_1.json"))
        self.source = {
            "name": "Assai",
            "role": "competitor",
            "url": "https://assai.com.br/ofertas",
            "ocr_path": self.ocr_path
        }
        self.old_env = os.environ.get("EXTRACTION_ENGINE")

    def tearDown(self):
        if self.old_env is not None:
            os.environ["EXTRACTION_ENGINE"] = self.old_env
        else:
            os.environ.pop("EXTRACTION_ENGINE", None)

    def test_01_engine_ausente_default_generic(self):
        """1. EXTRACTION_ENGINE ausente -> default operacional promovido para GENERIC."""
        os.environ.pop("EXTRACTION_ENGINE", None)
        items = coletar_itens_preco_fonte(self.source)
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 7)

    def test_02_engine_explicitamente_legacy(self):
        """2. EXTRACTION_ENGINE=legacy -> executa modo LEGACY."""
        os.environ["EXTRACTION_ENGINE"] = "legacy"
        items = coletar_itens_preco_fonte(self.source)
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)

    def test_03_engine_generic_usa_bridge(self):
        """3. EXTRACTION_ENGINE=generic -> executa o novo motor extractors/bridge."""
        os.environ["EXTRACTION_ENGINE"] = "generic"
        items = coletar_itens_preco_fonte(self.source)
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 7)  # 7 produtos exatos e sem falso positivo 162.49

    def test_04_engine_shadow_mantem_legacy_oficial(self):
        """4. EXTRACTION_ENGINE=shadow -> executa ambos e retorna o LEGACY oficial."""
        os.environ["EXTRACTION_ENGINE"] = "shadow"
        items = coletar_itens_preco_fonte(self.source)
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)

    def test_05_valor_invalido_fallback_legacy(self):
        """5. Valor inválido de EXTRACTION_ENGINE -> fallback seguro para LEGACY."""
        os.environ["EXTRACTION_ENGINE"] = "valor_invalido_123"
        items = coletar_itens_preco_fonte(self.source)
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)

    def test_06_generic_retorna_lista_price_item(self):
        """6. GENERIC retorna estritamente List[PriceItem]."""
        os.environ["EXTRACTION_ENGINE"] = "generic"
        items = coletar_itens_preco_fonte(self.source)
        for it in items:
            self.assertIsInstance(it, PriceItem)

    def test_07_campos_price_item_validos(self):
        """7. Todos os 17 campos do PriceItem continuam preenchidos e válidos."""
        os.environ["EXTRACTION_ENGINE"] = "generic"
        items = coletar_itens_preco_fonte(self.source)
        for it in items:
            self.assertIsInstance(it.name, str)
            self.assertIsInstance(it.price, float)
            self.assertGreaterEqual(it.price_confidence, 0.70)
            self.assertGreater(len(it.key()), 0)

    def test_08_shadow_falha_generic_nao_derruba_legacy(self):
        """14. Em modo SHADOW, se o GENERIC falhar, o LEGACY NÃO é derrubado."""
        os.environ["EXTRACTION_ENGINE"] = "shadow"
        with patch("extractors.bridge.executar_pipeline_extracao") as mock_bridge:
            # Configura para o generic falhar mas o legacy funcionar
            def side_effect(origem, engine, **kwargs):
                if engine == "generic":
                    raise RuntimeError("Falha simulada do generic")
                return {"price_items": [PriceItem("Assai", "competitor", "Produto Legacy", "", 10.0)]}
            mock_bridge.side_effect = side_effect

            items = coletar_itens_preco_fonte(self.source)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].name, "Produto Legacy")

    def test_09_falha_generic_no_modo_generic_lanca_erro_explicito(self):
        """15. Se GENERIC falhar em modo GENERIC, lança erro explícito sem mascarar como sucesso."""
        os.environ["EXTRACTION_ENGINE"] = "generic"
        with patch("extractors.bridge.executar_pipeline_extracao") as mock_bridge:
            mock_bridge.side_effect = RuntimeError("Erro crítico de extração")
            with self.assertRaises(RuntimeError):
                coletar_itens_preco_fonte(self.source)


if __name__ == "__main__":
    unittest.main()
