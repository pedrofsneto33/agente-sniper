# -*- coding: utf-8 -*-
"""
Testes Unitários Exclusivos da Camada Storage / SQLite — Agente Sniper
Cobre: Schema, criação, leitura, persistência de runs, fontes, eventos, snapshots de preço,
cálculo de deltas, isolamento e validação de contratos em bancos temporários.
"""
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from domain.models import Fonte
from storage.sqlite import MemoriaSniper


class TestStorageLayer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sniper_storage_test_")
        self.temp_path = Path(self.temp_dir)
        self.db_file = self.temp_path / "test_storage.sqlite3"

        self.fontes = [
            Fonte(
                id=1,
                titulo="Supermercado Carvalho abre filial",
                url="https://carvalho.com.br/noticia1",
                origem="web",
                conteudo="Conteudo original da noticia 1",
                data_publicacao="2026-08-15",
                score=85.0,
                fingerprint="fp_carvalho_01",
                atual=True
            ),
            Fonte(
                id=2,
                titulo="Concorrente Mateus inaugura loja",
                url="https://mateus.com.br/noticia2",
                origem="web",
                conteudo="Conteudo original da noticia 2",
                data_publicacao="2026-08-14",
                score=80.0,
                fingerprint="fp_mateus_02",
                atual=True
            )
        ]

        self.events = [
            {
                "event_id": "EVT_01",
                "kind": "EXPANSÃO",
                "title": "Expansão de loja no Jockey",
                "importance": 78,
                "evidence_ids": [1],
                "date": "2026-08-15"
            }
        ]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_banco_vazio_e_schema(self):
        """Testa inicialização do schema e comportamento com banco vazio."""
        with MemoriaSniper(self.db_file) as mem:
            self.assertIsNone(mem.previous_run())
            # Verifica tabelas criadas no sqlite_master
            tables = [
                r[0] for r in mem.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            self.assertIn("runs", tables)
            self.assertIn("sources", tables)
            self.assertIn("events", tables)
            self.assertIn("price_snapshots", tables)

    def test_02_persistencia_e_leitura_de_run(self):
        """Testa gravação de run, fontes, eventos e leitura posterior."""
        with MemoriaSniper(self.db_file) as mem:
            stats = mem.save_run(
                run_id="RUN_2026_01",
                fontes=self.fontes,
                events=self.events,
                empresa="Supermercado Carvalho",
                nicho="supermercado",
                cidade="Teresina",
                estado="PI",
                created_at="2026-08-15T10:00:00"
            )
            self.assertIsNone(stats["previous_run"])
            self.assertEqual(stats["novas_fontes"], 0)
            self.assertEqual(mem.previous_run(), "RUN_2026_01")

            run_data = mem.get_run("RUN_2026_01")
            self.assertIsNotNone(run_data)
            self.assertEqual(run_data["empresa"], "Supermercado Carvalho")
            self.assertEqual(run_data["cidade"], "Teresina")

            sources = mem.get_sources("RUN_2026_01")
            self.assertEqual(len(sources), 2)
            self.assertEqual(sources[0]["fingerprint"], "fp_carvalho_01")

            events = mem.get_events("RUN_2026_01")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_key"], "EVT_01")
            self.assertEqual(events[0]["evidence_ids"], [1])

    def test_03_delta_entre_runs_novas_e_alteradas(self):
        """Testa detecção precisa de fontes novas e fontes cujo conteúdo foi modificado."""
        with MemoriaSniper(self.db_file) as mem:
            mem.save_run("RUN_01", self.fontes, self.events, created_at="2026-08-15T10:00:00")

            # Cria fonte alterada (mesmo fingerprint, conteudo alterado)
            fonte_alterada = Fonte(
                id=1,
                titulo="Supermercado Carvalho expande",
                url="https://carvalho.com.br/noticia1",
                origem="web",
                conteudo="Conteudo MODIFICADO da noticia 1",
                fingerprint="fp_carvalho_01"
            )
            # Cria fonte nova
            fonte_nova = Fonte(
                id=3,
                titulo="Novo concorrente chega",
                url="https://novo.com",
                origem="web",
                conteudo="Texto novissimo",
                fingerprint="fp_novo_03"
            )

            stats = mem.save_run("RUN_02", [fonte_alterada, fonte_nova], self.events, created_at="2026-08-16T10:00:00")
            self.assertEqual(stats["previous_run"], "RUN_01")
            self.assertEqual(stats["novas_fontes"], 1)
            self.assertEqual(stats["fontes_alteradas"], 1)

    def test_04_persistencia_price_snapshots_e_mudancas(self):
        """Testa gravação de snapshots de preços e cálculo de delta/promoções."""
        with MemoriaSniper(self.db_file) as mem:
            snapshots_1 = [
                {
                    "entity": "Supermercado Carvalho",
                    "role": "target",
                    "source_domain": "carvalho.com.br",
                    "product_key": "arroz_camil_1kg",
                    "product_name": "Arroz Camil 1kg",
                    "brand": "Camil",
                    "unit": "1kg",
                    "price": 6.00,
                    "old_price": 7.00,
                    "promotion": 1,
                    "url": "https://carvalho.com.br/arroz",
                    "location_note": "Teresina"
                }
            ]
            res1 = mem.save_price_snapshots("RUN_01", snapshots_1)
            mem.save_run("RUN_01", self.fontes, self.events, created_at="2026-08-15T10:00:00")
            self.assertEqual(res1["gravados"], 1)
            self.assertEqual(len(res1["mudancas"]), 0)

            # Execução 2: no motor real, save_price_snapshots ocorre antes de save_run da run atual
            snapshots_2 = [
                {
                    "entity": "Supermercado Carvalho",
                    "role": "target",
                    "source_domain": "carvalho.com.br",
                    "product_key": "arroz_camil_1kg",
                    "product_name": "Arroz Camil 1kg",
                    "brand": "Camil",
                    "unit": "1kg",
                    "price": 6.90,
                    "old_price": None,
                    "promotion": 0,
                    "url": "https://carvalho.com.br/arroz",
                    "location_note": "Teresina"
                }
            ]
            res2 = mem.save_price_snapshots("RUN_02", snapshots_2)
            mem.save_run("RUN_02", self.fontes, self.events, created_at="2026-08-16T10:00:00")
            self.assertEqual(res2["gravados"], 1)
            self.assertEqual(len(res2["mudancas"]), 1)
            mudanca = res2["mudancas"][0]
            self.assertEqual(mudanca["previous_price"], 6.00)
            self.assertEqual(mudanca["current_price"], 6.90)
            self.assertEqual(mudanca["change_pct"], 15.0)
            self.assertTrue(mudanca["promotion_before"])
            self.assertFalse(mudanca["promotion_now"])

    def test_05_validacao_evento_sem_id(self):
        """Testa lançamento de ValueError quando evento não possui event_id nem event_key."""
        with MemoriaSniper(self.db_file) as mem:
            evento_invalido = [{"kind": "EXPANSÃO", "title": "Sem chave"}]
            with self.assertRaises(ValueError):
                mem.save_run("RUN_ERR", self.fontes, evento_invalido)

    def test_06_isolamento_entre_bancos(self):
        """Garante que dois bancos temporários não compartilham estado."""
        db1 = self.temp_path / "banco1.sqlite3"
        db2 = self.temp_path / "banco2.sqlite3"

        with MemoriaSniper(db1) as m1, MemoriaSniper(db2) as m2:
            m1.save_run("RUN_B1", self.fontes, self.events)
            self.assertEqual(m1.previous_run(), "RUN_B1")
            self.assertIsNone(m2.previous_run())

    def test_07_default_min_change_pct_standalone(self):
        """Garante que a chamada standalone sem informar min_change_pct utiliza 0.5% como default."""
        with MemoriaSniper(self.db_file) as mem:
            snap_r1 = [
                {
                    "entity": "Supermercado Carvalho", "role": "target", "source_domain": "carvalho.com.br",
                    "product_key": "prod_a", "product_name": "Produto A", "brand": "Marca",
                    "unit": "1kg", "price": 10.00, "old_price": None, "promotion": 0,
                    "url": "https://a.com", "location_note": ""
                },
                {
                    "entity": "Supermercado Carvalho", "role": "target", "source_domain": "carvalho.com.br",
                    "product_key": "prod_b", "product_name": "Produto B", "brand": "Marca",
                    "unit": "1kg", "price": 10.00, "old_price": None, "promotion": 0,
                    "url": "https://b.com", "location_note": ""
                }
            ]
            mem.save_price_snapshots("RUN_01", snap_r1)
            mem.save_run("RUN_01", self.fontes, self.events, created_at="2026-08-15T10:00:00")

            # RUN_02:
            # Produto A: 10.00 -> 10.08 (+0.80%, > 0.5% e < 5.0%) -> DEVE ser capturado pelo default
            # Produto B: 10.00 -> 10.02 (+0.20%, < 0.5%) -> NÃO deve ser capturado
            snap_r2 = [
                {
                    "entity": "Supermercado Carvalho", "role": "target", "source_domain": "carvalho.com.br",
                    "product_key": "prod_a", "product_name": "Produto A", "brand": "Marca",
                    "unit": "1kg", "price": 10.08, "old_price": None, "promotion": 0,
                    "url": "https://a.com", "location_note": ""
                },
                {
                    "entity": "Supermercado Carvalho", "role": "target", "source_domain": "carvalho.com.br",
                    "product_key": "prod_b", "product_name": "Produto B", "brand": "Marca",
                    "unit": "1kg", "price": 10.02, "old_price": None, "promotion": 0,
                    "url": "https://b.com", "location_note": ""
                }
            ]
            # Chamada puramente standalone sem passar min_change_pct
            res = mem.save_price_snapshots("RUN_02", snap_r2)
            mem.save_run("RUN_02", self.fontes, self.events, created_at="2026-08-16T10:00:00")

            self.assertEqual(res["gravados"], 2)
            self.assertEqual(len(res["mudancas"]), 1)
            self.assertEqual(res["mudancas"][0]["product_key"], "prod_a")
            self.assertEqual(res["mudancas"][0]["change_pct"], 0.80)

