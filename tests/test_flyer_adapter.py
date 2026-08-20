# -*- coding: utf-8 -*-
"""
Testes Unitários do FlyerProductAdapter com Fixtures Sintéticas e Reais
"""

import json
import os
import unittest
from pathlib import Path

from extractors.models import (
    BoundingBox,
    SpatialToken,
    RawSpatialDocument,
)
from extractors.adapters.flyer_product_adapter import FlyerProductAdapter


class TestFlyerAdapter(unittest.TestCase):
    """Testa o adaptador especializado de encartes em dados sintéticos e fixtures reais."""

    def test_01_adapter_execucao_sintetica(self):
        """Testa o fluxo completo do adapter com produto sintético."""
        dimensoes = (1000.0, 2000.0)
        # Cabeçalho
        t_head = SpatialToken("OFERTAS DA SEMANA", BoundingBox(100, 50, 400, 100), id_token=1)
        # Produto 1
        t_prod1_titulo = SpatialToken("CAFÉ PILÃO ESPRESSO", BoundingBox(100, 400, 350, 450), id_token=2)
        t_prod1_peso = SpatialToken("PACOTE 500G", BoundingBox(100, 460, 250, 490), id_token=3)
        t_prod1_preco = SpatialToken("R$ 18,90 CADA", BoundingBox(100, 500, 250, 550), id_token=4)
        # Produto 2
        t_prod2_titulo = SpatialToken("AÇÚCAR REFINADO UNIÃO", BoundingBox(600, 400, 850, 450), id_token=5)
        t_prod2_peso = SpatialToken("PACOTE 1KG", BoundingBox(600, 460, 750, 490), id_token=6)
        t_prod2_preco = SpatialToken("4,79", BoundingBox(600, 500, 700, 550), id_token=7)
        # Rodapé
        t_foot = SpatialToken("PREÇOS VÁLIDOS ENQUANTO DURAREM OS ESTOQUES", BoundingBox(100, 1900, 800, 1950), id_token=8)

        doc = RawSpatialDocument(
            identificador="doc_flyer_synth",
            origem="synth",
            dimensoes=dimensoes,
            tokens=[t_head, t_prod1_titulo, t_prod1_peso, t_prod1_preco, t_prod2_titulo, t_prod2_peso, t_prod2_preco, t_foot]
        )

        adapter = FlyerProductAdapter(topo_exclusao_rel=0.10, rodape_exclusao_rel=0.90)
        res = adapter.processar_documento(doc)

        self.assertEqual(res.total_entidades, 2)
        valores = [e.valor for e in res.entidades]
        self.assertIn(18.90, valores)
        self.assertIn(4.79, valores)

        for e in res.entidades:
            self.assertEqual(e.entidade, "produto")
            self.assertEqual(e.unidade, "BRL")
            self.assertGreater(len(e.evidencias), 0)

    def test_02_fixture_real_49738_sem_falso_positivo_peso(self):
        """Testa o adapter contra o fixture real ocr_bruto/49738-102_pagina_1.json."""
        caminho_fixture = Path(r"dados_browser/ocr_bruto\49738-102_pagina_1.json")
        if not caminho_fixture.exists():
            self.skipTest("Fixture real 49738 não encontrada.")

        with open(caminho_fixture, "r", encoding="utf-8") as f:
            data = json.load(f)

        deteccoes = data.get("deteccoes", [])
        tokens = []
        max_x = max((d["x_max"] for d in deteccoes), default=2000.0)
        max_y = max((d["y_max"] for d in deteccoes), default=3000.0)

        for d in deteccoes:
            bbox = BoundingBox(d["x_min"], d["y_min"], d["x_max"], d["y_max"])
            tokens.append(SpatialToken(texto=d["texto"], bbox=bbox, confianca=d.get("confianca", 1.0), id_token=d["id"]))

        doc = RawSpatialDocument(identificador="49738-102_pagina_1", origem="ocr_bruto", dimensoes=(max_x, max_y), tokens=tokens)

        adapter = FlyerProductAdapter()
        resultado = adapter.processar_documento(doc)

        # Propriedades de qualidade validadas:
        # 1. Total de entidades produzidas deve ser consistente com o número de preços reais (6 a 8)
        self.assertGreaterEqual(resultado.total_entidades, 6)
        self.assertLessEqual(resultado.total_entidades, 8)

        valores = [e.valor for e in resultado.entidades]

        # 2. Preços centrais verdadeiros devem estar presentes
        self.assertIn(17.90, valores)
        self.assertIn(3.29, valores)
        self.assertIn(23.90, valores)
        self.assertIn(25.90, valores)
        self.assertIn(6.19, valores)
        self.assertIn(85.90, valores)

        # 3. O FALSO PREÇO de 162.4 (peso de 162,4g) NÃO PODE existir como entidade
        self.assertNotIn(162.4, valores)
        self.assertNotIn(156.8, valores)

        # 4. Toda entidade deve ter evidências e coordenadas válidas
        for ent in resultado.entidades:
            self.assertGreater(len(ent.evidencias), 0)
            self.assertIsNotNone(ent.atributos.get("nome"))
            self.assertGreater(ent.confianca, 0.0)

    def test_03_fixture_real_49794_automotivo(self):
        """Testa o adapter contra o fixture real ocr_bruto/49794-102_pagina_1.json."""
        caminho_fixture = Path(r"dados_browser/ocr_bruto\49794-102_pagina_1.json")
        if not caminho_fixture.exists():
            self.skipTest("Fixture real 49794 não encontrada.")

        with open(caminho_fixture, "r", encoding="utf-8") as f:
            data = json.load(f)

        deteccoes = data.get("deteccoes", [])
        tokens = []
        max_x = max((d["x_max"] for d in deteccoes), default=2000.0)
        max_y = max((d["y_max"] for d in deteccoes), default=3000.0)

        for d in deteccoes:
            bbox = BoundingBox(d["x_min"], d["y_min"], d["x_max"], d["y_max"])
            tokens.append(SpatialToken(texto=d["texto"], bbox=bbox, confianca=d.get("confianca", 1.0), id_token=d["id"]))

        doc = RawSpatialDocument(identificador="49794-102_pagina_1", origem="ocr_bruto", dimensoes=(max_x, max_y), tokens=tokens)

        adapter = FlyerProductAdapter()
        resultado = adapter.processar_documento(doc)

        # Valida detecção de produtos automotivos
        self.assertGreaterEqual(resultado.total_entidades, 6)
        valores = [e.valor for e in resultado.entidades]

        # Pneus e óleos
        self.assertIn(349.90, valores)
        self.assertIn(389.90, valores)
        self.assertIn(279.90, valores)
        self.assertIn(21.90, valores)
        self.assertIn(34.90, valores)


if __name__ == "__main__":
    unittest.main()
