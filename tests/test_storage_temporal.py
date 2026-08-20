# -*- coding: utf-8 -*-
"""
Suíte de Testes Formais para Persistência Multi-Run e Histórico Temporal SQLite (Fase 33 / Etapa 3).
Cobre:
1. Banco vazio (listas vazias e dicionários vazios sem exceções)
2. save_run() primeira execução (classificação NOVO)
3. save_run() segunda execução (classificação RECORRENTE)
4. save_run() evento expirado (> 45 dias) -> INATIVO_EXPIRADO
5. get_event_history() ordenação determinística e limit_runs
6. get_event_history() filtro since
7. get_all_price_snapshots() multi-run e filtros por entity
8. get_price_series() integração ponta-a-ponta com cálculo de séries temporais
9. Retrocompatibilidade estrita das chaves de retorno de save_run() e save_price_snapshots()
10. Isolamento entre múltiplos bancos temporários
11. Histórico de eventos com mais de 10 runs dentro da janela de 45 dias (sem truncamento por heurística)
12. Desempate estritamente determinístico de snapshots por run_id
13. Semântica de since em get_all_price_snapshots() baseada em captured_at (mesmo quando run.created_at difere)
"""

import sys
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.models import Fonte
from domain.deltas import (
    ESTADO_EVENTO_NOVO,
    ESTADO_EVENTO_RECORRENTE,
    ESTADO_EVENTO_INATIVO_EXPIRADO,
)
from storage.sqlite import MemoriaSniper


class TestStorageTemporal(unittest.TestCase):
    """Testes unitários formais para a persistência e consulta temporal multi-run em SQLite."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sniper_storage_temporal_test_")
        self.temp_path = Path(self.temp_dir)
        self.db_file = self.temp_path / "test_temporal.sqlite3"

        self.fontes_base = [
            Fonte(
                id=1,
                titulo="Mateus abre atacarejo",
                url="https://mateus.com.br/1",
                origem="web",
                conteudo="Conteudo 1",
                fingerprint="fp_01",
                score=80.0,
                atual=True
            )
        ]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_banco_vazio_retornos(self):
        """1. Banco vazio retorna listas vazias e dicionário vazio sem erros."""
        with MemoriaSniper(self.db_file) as mem:
            self.assertEqual(mem.get_event_history(), [])
            self.assertEqual(mem.get_all_price_snapshots(), [])
            self.assertEqual(mem.get_price_series(), {})

    def test_02_save_run_primeira_execucao_delta_novo(self):
        """2. Primeira execução classifica eventos como NOVO em eventos_delta."""
        events_r1 = [
            {"event_id": "ev_01", "event_key": "k_01", "kind": "EXPANSÃO", "title": "Inauguração Timon", "importance": 70, "date": "2026-08-15"}
        ]
        with MemoriaSniper(self.db_file) as mem:
            stats = mem.save_run("RUN_01", self.fontes_base, events_r1, created_at="2026-08-15T10:00:00")
            self.assertIsNone(stats["previous_run"])
            self.assertIn("eventos_delta", stats)
            delta = stats["eventos_delta"]
            self.assertEqual(len(delta["novos"]), 1)
            self.assertEqual(delta["novos"][0]["estado_temporal"], ESTADO_EVENTO_NOVO)
            self.assertEqual(len(delta["recorrentes"]), 0)

    def test_03_save_run_segunda_execucao_delta_recorrente(self):
        """3. Segunda execução com mesmo evento classifica como RECORRENTE em eventos_delta."""
        events = [
            {"event_id": "ev_01", "event_key": "k_01", "kind": "EXPANSÃO", "title": "Inauguração Timon", "importance": 70, "date": "2026-08-15"}
        ]
        with MemoriaSniper(self.db_file) as mem:
            mem.save_run("RUN_01", self.fontes_base, events, created_at="2026-08-15T10:00:00")
            stats2 = mem.save_run("RUN_02", self.fontes_base, events, created_at="2026-08-16T10:00:00")
            self.assertEqual(stats2["previous_run"], "RUN_01")
            delta = stats2["eventos_delta"]
            self.assertEqual(len(delta["recorrentes"]), 1)
            self.assertEqual(delta["recorrentes"][0]["estado_temporal"], ESTADO_EVENTO_RECORRENTE)
            self.assertEqual(len(delta["novos"]), 0)

    def test_04_save_run_evento_expirado(self):
        """4. Evento histórico sem nova evidência com mais de 45 dias é identificado em expirados."""
        ev_antigo = [
            {"event_id": "ev_old", "event_key": "k_old", "kind": "MARKETING", "title": "Campanha Antiga", "importance": 50, "date": "2026-06-01"}
        ]
        ev_novo = [
            {"event_id": "ev_new", "event_key": "k_new", "kind": "EXPANSÃO", "title": "Nova Loja", "importance": 70, "date": "2026-08-20"}
        ]
        with MemoriaSniper(self.db_file) as mem:
            mem.save_run("RUN_01", self.fontes_base, ev_antigo, created_at="2026-06-01T10:00:00")
            stats = mem.save_run("RUN_02", self.fontes_base, ev_novo, created_at="2026-08-20T10:00:00")
            delta = stats["eventos_delta"]
            self.assertEqual(len(delta["novos"]), 1)
            self.assertEqual(len(delta["expirados"]), 1)
            self.assertEqual(delta["expirados"][0]["estado_temporal"], ESTADO_EVENTO_INATIVO_EXPIRADO)

    def test_05_get_event_history_ordenacao_e_limit_runs(self):
        """5. get_event_history recupera eventos ordenados deterministicamente e respeita limit_runs."""
        with MemoriaSniper(self.db_file) as mem:
            mem.save_run("RUN_01", [], [{"event_id": "ev_1", "kind": "EXPANSÃO", "title": "E1"}], created_at="2026-08-10T10:00:00")
            mem.save_run("RUN_02", [], [{"event_id": "ev_2", "kind": "PREÇO", "title": "E2"}], created_at="2026-08-12T10:00:00")
            mem.save_run("RUN_03", [], [{"event_id": "ev_3", "kind": "DIGITAL", "title": "E3"}], created_at="2026-08-14T10:00:00")

            # limit_runs=2 deve pegar as 2 runs mais recentes (RUN_03, RUN_02)
            hist = mem.get_event_history(limit_runs=2)
            self.assertEqual(len(hist), 2)
            keys = [e["event_key"] for e in hist]
            self.assertEqual(keys, ["ev_2", "ev_3"])

    def test_06_get_event_history_filtro_since(self):
        """6. get_event_history filtra por data mínima since."""
        with MemoriaSniper(self.db_file) as mem:
            mem.save_run("RUN_01", [], [{"event_id": "ev_1", "kind": "EXPANSÃO", "title": "E1"}], created_at="2026-08-01T10:00:00")
            mem.save_run("RUN_02", [], [{"event_id": "ev_2", "kind": "EXPANSÃO", "title": "E2"}], created_at="2026-08-15T10:00:00")

            hist = mem.get_event_history(since="2026-08-10")
            self.assertEqual(len(hist), 1)
            self.assertEqual(hist[0]["event_key"], "ev_2")

    def test_07_get_all_price_snapshots_multi_run_e_filtros(self):
        """7. get_all_price_snapshots recupera snapshots multi-run ordenados e filtra por entity."""
        snaps_r1 = [
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "arroz", "price": 5.0, "captured_at": "2026-08-01T08:00:00"},
            {"entity": "Carvalho", "source_domain": "carvalho.com", "product_key": "arroz", "price": 5.2, "captured_at": "2026-08-01T08:00:00"},
        ]
        snaps_r2 = [
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "arroz", "price": 5.5, "captured_at": "2026-08-15T08:00:00"},
        ]
        with MemoriaSniper(self.db_file) as mem:
            mem.save_price_snapshots("RUN_01", snaps_r1, captured_at="2026-08-01T08:00:00")
            mem.save_run("RUN_01", [], [], created_at="2026-08-01T08:00:00")
            mem.save_price_snapshots("RUN_02", snaps_r2, captured_at="2026-08-15T08:00:00")
            mem.save_run("RUN_02", [], [], created_at="2026-08-15T08:00:00")

            all_snaps = mem.get_all_price_snapshots()
            self.assertEqual(len(all_snaps), 3)

            mateus_snaps = mem.get_all_price_snapshots(entity="Mateus")
            self.assertEqual(len(mateus_snaps), 2)
            self.assertEqual(mateus_snaps[0]["price"], 5.0)
            self.assertEqual(mateus_snaps[1]["price"], 5.5)

    def test_08_get_price_series_integracao_completa(self):
        """8. get_price_series calcula deltas temporais 7d, 15d, 30d, volatilidade e tendência a partir do SQLite."""
        datas = ["2026-07-21", "2026-08-05", "2026-08-14", "2026-08-20"]
        precos = [10.0, 11.0, 11.5, 12.0]

        with MemoriaSniper(self.db_file) as mem:
            for i, (d, p) in enumerate(zip(datas, precos), 1):
                run_id = f"RUN_0{i}"
                snap = [{"entity": "Mateus", "source_domain": "mateus.com", "product_key": "leite", "product_name": "Leite 1L", "price": p, "captured_at": f"{d}T08:00:00"}]
                mem.save_price_snapshots(run_id, snap, captured_at=f"{d}T08:00:00")
                mem.save_run(run_id, [], [], created_at=f"{d}T08:00:00")

            series = mem.get_price_series(hoje=datetime(2026, 8, 20))
            key = ("Mateus", "mateus.com", "leite")
            self.assertIn(key, series)
            res = series[key]
            self.assertEqual(res["preco_atual"], 12.0)
            self.assertEqual(res["preco_anterior"], 11.5)
            self.assertEqual(res["pontos_observados"], 4)
            self.assertEqual(res["tendencia"], "ALTA")
            self.assertIsNotNone(res["deltas_janela"][7])
            self.assertIsNotNone(res["deltas_janela"][15])
            self.assertIsNotNone(res["deltas_janela"][30])

    def test_09_retrocompatibilidade_save_run_e_save_price(self):
        """9. Garante que save_run e save_price_snapshots mantêm todas as chaves obrigatórias tradicionais."""
        with MemoriaSniper(self.db_file) as mem:
            r1_price = mem.save_price_snapshots("RUN_01", [{"entity": "Mateus", "source_domain": "mateus.com", "product_key": "a", "price": 5.0}])
            r1_run = mem.save_run("RUN_01", self.fontes_base, [{"event_id": "ev1", "kind": "EXPANSÃO", "title": "T1"}])

            self.assertIn("previous_run", r1_price)
            self.assertIn("gravados", r1_price)
            self.assertIn("mudancas", r1_price)

            self.assertIn("previous_run", r1_run)
            self.assertIn("novas_fontes", r1_run)
            self.assertIn("fontes_alteradas", r1_run)
            self.assertIn("eventos_delta", r1_run)

    def test_10_isolamento_entre_bancos_temporarios(self):
        """10. Garante que dois bancos distintos não compartilham séries nem histórico de eventos."""
        db1 = self.temp_path / "b1.sqlite3"
        db2 = self.temp_path / "b2.sqlite3"

        with MemoriaSniper(db1) as m1, MemoriaSniper(db2) as m2:
            m1.save_run("RUN_1", [], [{"event_id": "e1", "kind": "EXPANSÃO", "title": "B1"}])
            self.assertEqual(len(m1.get_event_history()), 1)
            self.assertEqual(len(m2.get_event_history()), 0)

    def test_11_historico_mais_de_10_runs_na_janela_45_dias(self):
        """11. Prova que evento na 1ª run é recuperado e classificado como RECORRENTE mesmo após 12 runs intermediárias."""
        with MemoriaSniper(self.db_file) as mem:
            # Run 00: 20 dias atrás com evento ev_target
            data_inicial = datetime(2026, 8, 1)
            mem.save_run(
                "RUN_00",
                self.fontes_base,
                [{"event_id": "ev_target", "event_key": "k_target", "kind": "EXPANSÃO", "title": "Abertura Filial Sul", "importance": 80, "date": "2026-08-01"}],
                created_at="2026-08-01T10:00:00"
            )

            # Cria 12 runs intermediárias dentro dos dias seguintes (totalizando 13 runs anteriores)
            for i in range(1, 13):
                dt_i = data_inicial + timedelta(days=i)
                mem.save_run(
                    f"RUN_{i:02d}",
                    self.fontes_base,
                    [{"event_id": f"ev_misc_{i}", "kind": "PREÇO", "title": f"Misc {i}", "importance": 40, "date": dt_i.strftime("%Y-%m-%d")}],
                    created_at=f"{dt_i.strftime('%Y-%m-%d')}T10:00:00"
                )

            # Run 14: no dia 2026-08-20 (19 dias após a RUN_00, dentro dos 45 dias)
            # Reobserva o ev_target. Ele DEVE ser classificado como RECORRENTE mesmo estando a 13 runs de distância!
            stats_final = mem.save_run(
                "RUN_FINAL",
                self.fontes_base,
                [{"event_id": "ev_target", "event_key": "k_target", "kind": "EXPANSÃO", "title": "Abertura Filial Sul", "importance": 80, "date": "2026-08-20"}],
                created_at="2026-08-20T10:00:00"
            )

            delta = stats_final["eventos_delta"]
            self.assertEqual(len(delta["recorrentes"]), 1, "ev_target além da 10ª run deve ser pareado como RECORRENTE")
            self.assertEqual(delta["recorrentes"][0]["evento_origem_id"], "ev_target")
            self.assertEqual(len(delta["novos"]), 0)

    def test_12_desempate_deterministico_snapshots_por_run_id(self):
        """12. Prova que snapshots com mesmo (captured_at, entity, source_domain, product_key) desempatam por run_id ASC."""
        snap_a = [{"entity": "Mateus", "source_domain": "m.com", "product_key": "feijao", "price": 8.0, "captured_at": "2026-08-20T08:00:00"}]
        snap_b = [{"entity": "Mateus", "source_domain": "m.com", "product_key": "feijao", "price": 8.5, "captured_at": "2026-08-20T08:00:00"}]

        with MemoriaSniper(self.db_file) as mem:
            # Gravados em ordem inversa de run_id (RUN_Z gravado antes de RUN_A)
            mem.save_price_snapshots("RUN_Z", snap_b, captured_at="2026-08-20T08:00:00")
            mem.save_run("RUN_Z", [], [], created_at="2026-08-20T08:00:00")

            mem.save_price_snapshots("RUN_A", snap_a, captured_at="2026-08-20T08:00:00")
            mem.save_run("RUN_A", [], [], created_at="2026-08-20T08:00:00")

            snaps = mem.get_all_price_snapshots()
            self.assertEqual(len(snaps), 2)
            # Desempate estrito: RUN_A deve vir antes de RUN_Z
            self.assertEqual(snaps[0]["run_id"], "RUN_A")
            self.assertEqual(snaps[0]["price"], 8.0)
            self.assertEqual(snaps[1]["run_id"], "RUN_Z")
            self.assertEqual(snaps[1]["price"], 8.5)

    def test_13_since_baseado_em_captured_at_independente_de_created_at(self):
        """13. Prova que get_all_price_snapshots filtra por captured_at mesmo quando run.created_at difere."""
        with MemoriaSniper(self.db_file) as mem:
            # Snapshot capturado em 2026-08-10, persistido numa run de 2026-08-20
            snap_antigo = [{"entity": "Carvalho", "source_domain": "c.com", "product_key": "oleo", "price": 6.0, "captured_at": "2026-08-10T12:00:00"}]
            mem.save_price_snapshots("RUN_20", snap_antigo, captured_at="2026-08-10T12:00:00")
            mem.save_run("RUN_20", [], [], created_at="2026-08-20T10:00:00")

            # Snapshot capturado em 2026-08-18, persistido numa run de 2026-08-20
            snap_recente = [{"entity": "Carvalho", "source_domain": "c.com", "product_key": "oleo", "price": 6.5, "captured_at": "2026-08-18T12:00:00"}]
            mem.save_price_snapshots("RUN_21", snap_recente, captured_at="2026-08-18T12:00:00")
            mem.save_run("RUN_21", [], [], created_at="2026-08-20T11:00:00")

            # Filtro since="2026-08-15": deve retornar APENAS o snap_recente (captured_at >= 2026-08-15)
            # mesmo que ambas as runs tenham created_at em 2026-08-20!
            res = mem.get_all_price_snapshots(since="2026-08-15")
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["captured_at"], "2026-08-18T12:00:00")
            self.assertEqual(res[0]["price"], 6.5)


if __name__ == "__main__":
    unittest.main()
