# -*- coding: utf-8 -*-
"""
Bateria de Testes de Robustez e Idempotência da Ponte (Bridge) — Fase 5
Testa resiliência extrema: OCR vazio, BBox inválido, Unicode, ausência de confiança,
100s de entidades, fragmentação e determinismo estrito (Idempotência).
"""

import json
import unittest
from pathlib import Path

from extractors.models import (
    BoundingBox,
    SpatialToken,
    RawSpatialDocument,
)
from extractors.bridge import (
    carregar_ocr_bruto,
    executar_pipeline_extracao,
    converter_entidades_para_price_items,
    converter_para_schema_legacy_cards,
)
from extractors.adapters.flyer_product_adapter import FlyerProductAdapter


class TestShadowRobustness(unittest.TestCase):
    """Testa resiliência da ponte sob entradas corrompidas ou extremas."""

    def test_01_ocr_vazio_sem_crash(self):
        """Garante que OCR com lista de detecções vazia retorna lista vazia de forma segura."""
        doc_vazio = {"arquivo": "vazio.jpeg", "total_deteccoes": 0, "deteccoes": []}
        res = executar_pipeline_extracao(doc_vazio, engine="generic")
        self.assertEqual(res["total_itens"], 0)
        self.assertEqual(len(res["price_items"]), 0)

    def test_02_token_sem_bbox_e_texto_vazio(self):
        """Testa documento contendo tokens sem BBox, textos nulos e vazios."""
        t1 = SpatialToken(texto="", bbox=None, confianca=0.9, id_token=1)
        t2 = SpatialToken(texto="   ", bbox=BoundingBox(0, 0, 0, 0), confianca=0.9, id_token=2)
        t3 = SpatialToken(texto="PRODUTO VALIDO", bbox=BoundingBox(100, 300, 300, 330), confianca=0.9, id_token=3)
        t4 = SpatialToken(texto="R$ 19,90", bbox=BoundingBox(100, 340, 200, 370), confianca=0.9, id_token=4)

        doc = RawSpatialDocument("doc_edge", "synth", (1000, 1000), [t1, t2, t3, t4])
        adapter = FlyerProductAdapter()
        resultado = adapter.processar_documento(doc)

        self.assertEqual(resultado.total_entidades, 1)
        self.assertEqual(resultado.entidades[0].valor, 19.90)

    def test_03_bbox_invalido_auto_correcao(self):
        """Garante que BBox invertida (x_min > x_max) é auto-corrigida sem quebrar."""
        box_inv = BoundingBox(x_min=500.0, y_min=600.0, x_max=100.0, y_max=200.0)
        self.assertEqual(box_inv.x_min, 100.0)
        self.assertEqual(box_inv.x_max, 500.0)
        self.assertEqual(box_inv.y_min, 200.0)
        self.assertEqual(box_inv.y_max, 600.0)

    def test_04_caracteres_unicode_e_acentos_complexos(self):
        """Testa suporte a strings complexas: apóstrofos, travessões, símbolos e acentos."""
        t1 = SpatialToken("CÁPSULAS L'OR ESPRESSO & PILÃO — 100% ARÁBICA", BoundingBox(100, 300, 500, 330), id_token=1)
        t2 = SpatialToken("R$ 24,90 CADA", BoundingBox(100, 340, 250, 370), id_token=2)
        doc = RawSpatialDocument("doc_unicode", "synth", (1000, 1000), [t1, t2])

        res = FlyerProductAdapter().processar_documento(doc)
        self.assertEqual(res.total_entidades, 1)
        self.assertIn("L'OR", res.entidades[0].atributos["nome"])
        self.assertEqual(res.entidades[0].valor, 24.90)

    def test_05_estresse_centenas_de_entidades(self):
        """Testa estabilidade e performance com 100 entidades geradas sinteticamente."""
        tokens = []
        token_id = 1
        for i in range(100):
            y_base = 200.0 + i * 50.0
            tokens.append(SpatialToken(f"PRODUTO NUMERO {i+1}", BoundingBox(100, y_base, 400, y_base + 20), id_token=token_id))
            token_id += 1
            tokens.append(SpatialToken(f"R$ {10.0 + i:.2f}", BoundingBox(100, y_base + 25, 250, y_base + 45), id_token=token_id))
            token_id += 1

        doc = RawSpatialDocument("doc_estresse_100", "synth", (2000, 10000), tokens)
        res = FlyerProductAdapter(topo_exclusao_rel=0.0, rodape_exclusao_rel=1.0).processar_documento(doc)

        self.assertEqual(res.total_entidades, 100)
        self.assertEqual(res.entidades[0].valor, 10.00)
        self.assertEqual(res.entidades[-1].valor, 109.00)

    def test_06_idempotencia_estrita_execucao_dupla(self):
        """Garante que duas execuções sucessivas do mesmo documento geram saídas 100% idênticas."""
        caminho_ocr = Path(r"C:\Users\User\Desktop\Agente sniper\dados_browser\ocr_bruto\49738-102_pagina_1.json")
        if not caminho_ocr.exists():
            self.skipTest("Fixture real não encontrada.")

        # Execução 1
        res1 = executar_pipeline_extracao(caminho_ocr, engine="generic")
        json1 = json.dumps([p.__dict__ for p in res1["price_items"]], sort_keys=True)

        # Execução 2
        res2 = executar_pipeline_extracao(caminho_ocr, engine="generic")
        json2 = json.dumps([p.__dict__ for p in res2["price_items"]], sort_keys=True)

        self.assertEqual(json1, json2)
        self.assertEqual(len(res1["price_items"]), len(res2["price_items"]))


if __name__ == "__main__":
    unittest.main()
