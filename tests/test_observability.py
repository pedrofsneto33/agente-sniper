# -*- coding: utf-8 -*-
"""
Testes Unit?rios de Observabilidade Operacional ? Fase 8
Valida persist?ncia append-only, fail-safe, leitura, percentis, crashes e integridade SQLite.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from extractors.observability import (
    OperationalRunRecord,
    OperationalMetricsTracker,
)
from extractors.promotion_gate import calcular_sha256_arquivo


class TestObservability(unittest.TestCase):
    """Su?te de testes para o m?dulo de observabilidade operacional."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmpdir.name) / "test_operational_metrics.jsonl"
        self.tracker = OperationalMetricsTracker(self.log_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_01_registro_execucao_estrutura(self):
        """1. Valida estrutura do registro e convers?o para dict."""
        rec = OperationalRunRecord(
            run_id="run_test_01",
            engine="generic",
            source="Assai",
            document_id="49738-102_pagina_1.json",
            document_hash="HASH123",
            extraction={"itens_validos": 7, "itens_descartados": 0},
            quality={"fp_generic": 0, "fn_generic": 0},
            reliability={"crashes": 0, "exceptions": 0},
            performance={"latencia_extracao_ms": 4.5}
        )
        d = rec.to_dict()
        self.assertEqual(d["run_id"], "run_test_01")
        self.assertEqual(d["engine"], "generic")
        self.assertEqual(d["extraction"]["itens_validos"], 7)

    def test_02_persistencia_append_only(self):
        """2. Valida persist?ncia append-only em JSONL."""
        rec1 = OperationalRunRecord(run_id="run_1", document_id="doc1")
        rec2 = OperationalRunRecord(run_id="run_1", document_id="doc2")
        self.assertTrue(self.tracker.registrar_execucao(rec1))
        self.assertTrue(self.tracker.registrar_execucao(rec2))

        lines = self.log_path.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["document_id"], "doc1")
        self.assertEqual(json.loads(lines[1])["document_id"], "doc2")

    def test_03_leitura_e_filtro_por_run_id(self):
        """3. Valida leitura e filtragem por run_id."""
        self.tracker.registrar_execucao(OperationalRunRecord(run_id="run_A", document_id="docA"))
        self.tracker.registrar_execucao(OperationalRunRecord(run_id="run_B", document_id="docB"))

        todas = self.tracker.obter_execucoes()
        self.assertEqual(len(todas), 2)

        filtro_a = self.tracker.obter_execucoes(filtro_run_id="run_A")
        self.assertEqual(len(filtro_a), 1)
        self.assertEqual(filtro_a[0]["document_id"], "docA")

    def test_04_idempotencia_leitura_e_agregacao(self):
        """4. Garante que leituras consecutivas produzem resultados id?nticos."""
        self.tracker.registrar_execucao(OperationalRunRecord(
            run_id="run_idemp",
            document_hash="HASH_1",
            extraction={"itens_validos": 5},
            performance={"latencia_extracao_ms": 3.0}
        ))
        res1 = self.tracker.obter_resumo_metricas()
        res2 = self.tracker.obter_resumo_metricas()
        self.assertEqual(res1, res2)
        self.assertEqual(res1["total_registros"], 1)
        self.assertEqual(res1["total_itens"], 5)

    def test_05_calculo_percentis_latencia(self):
        """5. Valida c?lculo consolidado de percentis P50/P95/P99/MAX."""
        latencias = [2.0, 3.0, 4.0, 5.0, 10.0]
        for idx, lat in enumerate(latencias):
            self.tracker.registrar_execucao(OperationalRunRecord(
                run_id="run_perf",
                document_id=f"doc_{idx}",
                performance={"latencia_extracao_ms": lat}
            ))
        res = self.tracker.obter_resumo_metricas(filtro_run_id="run_perf")
        perf = res["performance"]
        self.assertEqual(perf["max"], 10.0)
        self.assertGreater(perf["p99"], 0.0)
        self.assertGreater(perf["p50"], 0.0)

    def test_06_registro_erro_e_excecao(self):
        """6. Valida captura e agrega??o de exce??es operacionais."""
        self.tracker.registrar_execucao(OperationalRunRecord(
            run_id="run_err",
            reliability={"crashes": 0, "exceptions": 1, "error_msg": "Timeout simulado"}
        ))
        res = self.tracker.obter_resumo_metricas(filtro_run_id="run_err")
        self.assertEqual(res["erros"], 1)
        self.assertEqual(res["crashes"], 0)

    def test_07_registro_crash(self):
        """7. Valida registro de crash de extra??o."""
        self.tracker.registrar_execucao(OperationalRunRecord(
            run_id="run_crash",
            reliability={"crashes": 1, "exceptions": 1}
        ))
        res = self.tracker.obter_resumo_metricas(filtro_run_id="run_crash")
        self.assertEqual(res["crashes"], 1)

    def test_08_verificacao_integridade_sqlite(self):
        """8. Valida verificação de integridade do arquivo SQLite."""
        real_db = Path(r"C:\Users\User\Desktop\Agente sniper\sniper_resultados\sniper_historico.sqlite3")
        h = calcular_sha256_arquivo(real_db)
        res_db = OperationalMetricsTracker.verificar_integridade_sqlite(real_db, hash_esperado=h)
        self.assertTrue(res_db["valido"])
        self.assertEqual(res_db["hash"], h)

    def test_09_logger_fail_safe_sem_afetar_extracao(self):
        """9. Garante que falha no arquivo de log n?o lan?a exce??o para o chamador."""
        invalid_tracker = OperationalMetricsTracker(Path(r"Z:\diretorio_invalido_inexistente\log.jsonl"))
        sucesso = invalid_tracker.registrar_execucao(OperationalRunRecord(run_id="test_failsafe"))
        self.assertFalse(sucesso)


if __name__ == "__main__":
    unittest.main()
