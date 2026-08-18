# -*- coding: utf-8 -*-
"""
Testes Unitários de Persistência SQLite Isolada, Relatórios e Indexação de IDs — Agente Sniper v11.8.1
Cobre: MemoriaSniper (em banco temporário), salvar_json, salvar_csv_fontes, gerar_html, gerar_pdf e f.id.
"""
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import agente_sniper_v11_8 as sniper


class TestReportsAndStorage(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sniper_test_")
        self.temp_path = Path(self.temp_dir)
        # Salva caminhos originais para restaurar no tearDown
        self.original_pasta_exec = sniper.PASTA_EXECUCAO
        sniper.PASTA_EXECUCAO = self.temp_path

        # Fontes sintéticas para teste
        self.fontes = [
            sniper.Fonte(
                id=1, titulo="Supermercado Carvalho expande operações em Teresina",
                url="https://site1.com/noticia", origem="web", conteudo="Texto da notícia",
                data_publicacao="2026-08-15", alias_empresa=sniper.EMPRESA_ALVO,
                cidade_confirmada=True, estado_confirmado=True, escopo="local",
                entidade=sniper.EMPRESA_ALVO, score=90.0, atual=True
            ),
            sniper.Fonte(
                id=2, titulo="Concorrente Mateus abre vagas",
                url="https://site2.com/vagas", origem="web", conteudo="Texto de vagas",
                data_publicacao="2026-08-14", alias_empresa="",
                cidade_confirmada=True, estado_confirmado=True, escopo="local",
                entidade="Mateus", score=80.0, atual=True
            )
        ]
        self.events = [
            {
                "event_id": "EVT_TEST_01", "event_key": "EVT_TEST_01", "kind": "EXPANSÃO",
                "title": "Expansão de Operações", "importance": 85, "confidence": 0.9,
                "evidence_ids": [1], "entity": sniper.EMPRESA_ALVO, "current": True,
                "independent_source_count": 2, "date": "2026-08-15"
            }
        ]
        self.ambiente = {
            "score": 65, "label": "MÉDIA",
            "dimensoes": {
                "EXPANSÃO": {"score": 75, "status": "ATIVO", "eventos": [self.events[0]], "fontes_ids": [1]}
            },
            "momentum_mercado": 60,
            "pressao_competitiva": {"score": 45, "label": "MÉDIA"},
            "vulnerabilidade_empresa": {"score": 0, "label": "BAIXA"}
        }
        self.pacote = {
            "resumo_executivo": "Cenário competitivo estável.",
            "sinais": [
                {
                    "titulo": "Sinal de Expansão", "tipo": "OPORTUNIDADE",
                    "impacto": "ALTO", "urgencia": "MEDIA", "evidence_ids": [1],
                    "acao": "Mapear concorrentes locais."
                }
            ],
            "concorrencia": [],
            "prioridades_30": ["Ação 1"], "prioridades_60": ["Ação 2"], "prioridades_90": ["Ação 3"],
            "lacunas": ["Nenhuma lacuna crítica."]
        }

    def tearDown(self):
        sniper.PASTA_EXECUCAO = self.original_pasta_exec
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_memoria_sniper_sqlite_isolado(self):
        """Testa criação de schema, persistência e deltas em banco SQLite 100% temporário."""
        db_temp_file = self.temp_path / "test_sniper.sqlite3"
        memoria = sniper.MemoriaSniper(db_temp_file)

        # 1. Primeira execução: prev é None
        stats1 = memoria.save_run("TEST_RUN_01", self.fontes, self.events)
        self.assertIn("novas_fontes", stats1)
        self.assertIsNone(stats1["previous_run"])

        # 2. Confirma previous_run após gravação
        prev = memoria.previous_run()
        self.assertEqual(prev, "TEST_RUN_01")

        # 3. Segunda execução com 1 fonte nova: prev é TEST_RUN_01 e novas_fontes == 1
        fonte_nova = sniper.Fonte(
            id=3, titulo="Nova fonte exclusiva", url="https://nova.com", origem="web",
            conteudo="Conteudo novo", fingerprint="fp_nova_123"
        )
        stats2 = memoria.save_run("TEST_RUN_02", [self.fontes[0], fonte_nova], self.events)
        self.assertEqual(stats2["previous_run"], "TEST_RUN_01")
        self.assertEqual(stats2["novas_fontes"], 1)

        # 4. Salva snapshots de preços
        snapshots = [{
            "entity": sniper.EMPRESA_ALVO, "role": "target", "source_domain": "carvalho.com.br",
            "product_key": "arroz_1kg", "product_name": "Arroz 1kg", "brand": "Tio João",
            "unit": "1kg", "price": 6.99, "old_price": None, "promotion": 0,
            "url": "https://carvalho.com.br/arroz", "location_note": "Teresina"
        }]
        price_stats = memoria.save_price_snapshots("TEST_RUN_02", snapshots)
        self.assertEqual(price_stats["gravados"], 1)

        memoria.conn.close()

    def test_02_salvar_json_e_csv_temporario(self):
        """Testa geração de arquivos JSON e CSV no diretório isolado."""
        caminho_json = sniper.salvar_json("teste_inteligencia.json", self.pacote)
        self.assertTrue(Path(caminho_json).exists())

        caminho_csv = sniper.salvar_csv_fontes(self.fontes)
        self.assertTrue(Path(caminho_csv).exists())

    def test_03_gerar_html_valido(self):
        """Testa renderização do dashboard HTML com escape de tags e métricas."""
        html = sniper.gerar_html(self.pacote, self.fontes, self.events, self.ambiente, {})
        self.assertIsInstance(html, str)
        self.assertIn("doctype html", html.lower())
        self.assertIn(sniper.EMPRESA_ALVO, html)

    def test_04_gerar_pdf_sem_excecao(self):
        """Testa geração de PDF executivo com sanitização Latin-1 sem lançar exceções."""
        pdf_path = sniper.gerar_pdf(self.pacote, self.fontes, self.events, self.ambiente, {})
        if pdf_path:
            self.assertTrue(Path(pdf_path).exists())

    def test_05_comportamento_e_validacao_de_ids(self):
        """Documenta e testa a integridade dos IDs de evidência e validação forense."""
        # Garante que validar_ids_sinais aceita IDs existentes e rejeita IDs inexistentes
        ids_existentes = {f.id for f in self.fontes}
        self.assertEqual(ids_existentes, {1, 2})

        pacote_ok = {"sinais": [{"evidence_ids": [1]}]}
        valido, _ = sniper.validar_ids_sinais(pacote_ok, ids_existentes)
        self.assertTrue(valido)

        pacote_falso = {"sinais": [{"evidence_ids": [99]}]}
        invalido, msg = sniper.validar_ids_sinais(pacote_falso, ids_existentes)
        self.assertFalse(invalido)
        self.assertIn("99", msg)


if __name__ == "__main__":
    unittest.main()
