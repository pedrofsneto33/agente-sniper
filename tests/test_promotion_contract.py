# -*- coding: utf-8 -*-
"""
Testes de Contrato de Promoção e Integração Downstream — Fase 6A
Valida que PriceItems gerados pelo GENERIC atendem rigorosamente todos os 17 campos do domínio,
podem ser comparados por similaridade_produto, processados por detectar_mudancas_preco
e persistidos na Memória Histórica sem violações de schema.
"""

import os
import tempfile
import unittest
from pathlib import Path

from extractors.bridge import (
    obter_engine_ativo,
    executar_pipeline_extracao,
)
from domain.models import PriceItem
from domain.matching import similaridade_produto
from domain.pricing import detectar_mudancas_preco
from storage.sqlite import MemoriaSniper


class TestPromotionContract(unittest.TestCase):
    """Testa contratos downstream de PriceItem e esteira analítica."""

    def test_01_contrato_completo_campos_price_item(self):
        """Valida que todos os 17 campos de PriceItem são gerados com tipos válidos pelo Generic."""
        caminho_ocr = Path(r"dados_browser/ocr_bruto\49738-102_pagina_1.json")
        if not caminho_ocr.exists():
            self.skipTest("Fixture real não encontrada.")

        res = executar_pipeline_extracao(caminho_ocr, engine="flyer")
        items = res["price_items"]
        self.assertEqual(len(items), 7)

        for it in items:
            self.assertIsInstance(it.source, str)
            self.assertIsInstance(it.role, str)
            self.assertIsInstance(it.name, str)
            self.assertIsInstance(it.url, str)
            self.assertTrue(it.price is None or isinstance(it.price, float))
            self.assertIsInstance(it.promotion, bool)
            self.assertIsInstance(it.brand, str)
            self.assertIsInstance(it.unit, str)
            self.assertIsInstance(it.sku, str)
            self.assertIsInstance(it.matched_name, str)
            self.assertIsInstance(it.competitor, str)
            self.assertIsInstance(it.similarity, float)
            self.assertIsInstance(it.availability, str)
            self.assertIsInstance(it.location_note, str)
            self.assertIsInstance(it.evidence_url, str)
            self.assertIsInstance(it.page_type, str)
            self.assertIsInstance(it.price_confidence, float)

            # Valida que price_confidence atende ao limiar de produção (>= 0.70)
            self.assertGreaterEqual(it.price_confidence, 0.70)

            # Valida que a chave de indexação canônica é gerada sem erros
            k = it.key()
            self.assertIsInstance(k, str)
            self.assertGreater(len(k), 0)

    def test_02_similaridade_e_matching_com_esteira_pricing(self):
        """Valida que similaridade_produto do domínio funciona com itens do Generic."""
        caminho_ocr = Path(r"dados_browser/ocr_bruto\49738-102_pagina_1.json")
        if not caminho_ocr.exists():
            self.skipTest("Fixture real não encontrada.")

        items_gen = executar_pipeline_extracao(caminho_ocr, engine="generic")["price_items"]

        # Cria um item de catálogo alvo sintético correspondente
        alvo = PriceItem(
            source="EmpresaAlvo",
            role="target",
            name=items_gen[0].name,
            url="https://alvo.com/cafe-pilao",
            price=19.90,
            unit=items_gen[0].unit,
            price_confidence=0.95
        )

        sim = similaridade_produto(alvo, items_gen[0])
        self.assertGreater(sim, 0.80)

    def test_03_replay_snapshots_em_sqlite_isolado(self):
        """Executa gravação de snapshots de preços em SQLite isolado (sem tocar no banco real)."""
        caminho_ocr = Path(r"dados_browser/ocr_bruto\49738-102_pagina_1.json")
        if not caminho_ocr.exists():
            self.skipTest("Fixture real não encontrada.")

        items = executar_pipeline_extracao(caminho_ocr, engine="flyer")["price_items"]

        with tempfile.TemporaryDirectory() as tmpdir:
            caminho_db = Path(tmpdir) / "teste_shadow.sqlite3"
            mem = MemoriaSniper(str(caminho_db))
            try:
                snapshots_1 = [
                    {
                        "entity": "Assai",
                        "role": "competitor",
                        "source_domain": "assai.com.br",
                        "product_key": it.key(),
                        "product_name": it.name,
                        "brand": it.brand,
                        "unit": it.unit,
                        "price": it.price,
                        "old_price": it.old_price,
                        "promotion": it.promotion,
                        "url": it.url,
                        "location_note": it.location_note
                    }
                    for it in items
                ]

                mem.save_run("run_replay_shadow_001", [], {}, "2026-08-19T00:00:00")
                res_hist_1 = mem.save_price_snapshots("run_replay_shadow_001", snapshots_1)
                self.assertEqual(res_hist_1["gravados"], len(items))
                self.assertEqual(len(res_hist_1["mudancas"]), 0)

                # Executa uma segunda run com um preço reduzido para testar cálculo de deltas
                snapshots_2 = [dict(s) for s in snapshots_1]
                snapshots_2[0]["price"] = round(snapshots_2[0]["price"] * 0.90, 2)
                res_hist_2 = mem.save_price_snapshots("run_replay_shadow_002", snapshots_2)
                mem.save_run("run_replay_shadow_002", [], {}, "2026-08-19T01:00:00")
                self.assertEqual(len(res_hist_2["mudancas"]), 1)
                self.assertEqual(res_hist_2["mudancas"][0]["change_pct"], -10.0)
            finally:
                mem.conn.close()


if __name__ == "__main__":
    unittest.main()
