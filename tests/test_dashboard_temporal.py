# -*- coding: utf-8 -*-
"""
Suíte de Testes Formais para Integração da Inteligência Temporal com Dashboard e Orquestrador (Fase 33 / Etapa 4).
Cobre:
1. Renderização HTML com métricas de eventos_delta (novos, recorrentes) e badges temporais.
2. Renderização HTML com tabela de séries temporais de preços (Δ7d, Δ15d, Δ30d, volatilidade, tendência).
3. Fallback gracioso de renderização quando dados temporais estão vazios ou ausentes.
4. Integração de comparar_precos() com get_price_series() via MemoriaSniper.
5. Serialização JSON completa e limpa do payload executivo com dados temporais.
6. Geração de PDF com integridade de dados temporais.
"""

import sys
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import agente_sniper_v11_8 as sniper
from domain.models import Fonte


class TestDashboardTemporal(unittest.TestCase):
    """Testes unitários e de integração para apresentação dos dados temporais no Dashboard e Relatórios."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="sniper_dashboard_temporal_test_")
        self.temp_path = Path(self.temp_dir)
        self.original_pasta_exec = sniper.PASTA_EXECUCAO
        sniper.PASTA_EXECUCAO = self.temp_path

        self.fontes = [
            Fonte(
                id=1,
                titulo="Supermercado Carvalho expande operações em Teresina",
                url="https://site1.com/noticia",
                origem="web",
                conteudo="Texto da notícia",
                data_publicacao="2026-08-15",
                alias_empresa=sniper.EMPRESA_ALVO,
                cidade_confirmada=True,
                estado_confirmado=True,
                escopo="local",
                entidade=sniper.EMPRESA_ALVO,
                score=90.0,
                atual=True
            )
        ]

        self.events = [
            {
                "event_id": "EVT_01",
                "event_key": "EVT_01",
                "kind": "EXPANSÃO",
                "title": "Inauguração Nova Loja",
                "importance": 85,
                "confidence": 0.9,
                "evidence_ids": [1],
                "entity": sniper.EMPRESA_ALVO,
                "current": True,
                "independent_source_count": 2,
                "date": "2026-08-15",
                "estado_temporal": "NOVO"
            },
            {
                "event_id": "EVT_02",
                "event_key": "EVT_02",
                "kind": "PREÇO",
                "title": "Guerra de Ofertas Arroz",
                "importance": 75,
                "confidence": 0.85,
                "evidence_ids": [1],
                "entity": "Mateus",
                "current": True,
                "independent_source_count": 1,
                "date": "2026-08-14",
                "estado_temporal": "RECORRENTE"
            }
        ]

        self.ambiente = {
            "score": 65,
            "label": "MÉDIA",
            "dimensoes": {
                "EXPANSÃO": {"score": 75, "status": "ATIVO", "eventos": [self.events[0]], "evidencias": 1, "eventos_correlacionados": 1}
            },
            "momentum_mercado": 60,
            "pressao_competitiva": {"score": 45, "label": "MÉDIA"},
            "vulnerabilidade_empresa": {"score": 10, "label": "BAIXA"},
            "cobertura": 0.8
        }

        self.series_temporais = {
            "Carvalho::carvalho.com.br::arroz_5kg": {
                "entity": "Carvalho",
                "source_domain": "carvalho.com.br",
                "product_key": "arroz_5kg",
                "product_name": "Arroz Parboilizado 5kg",
                "preco_atual": 22.90,
                "preco_anterior": 24.50,
                "pontos_observados": 5,
                "volatilidade": 0.08,
                "tendencia": "QUEDA",
                "deltas_janela": {7: -6.5, 15: -8.0, 30: -10.2}
            }
        }

        self.comparacao_precos = {
            "enabled": True,
            "status": "ok",
            "produtos_alvo": 10,
            "comparaveis": 8,
            "alvo_mais_barato": 5,
            "concorrente_mais_barato": 3,
            "promocoes_alvo": 2,
            "promocoes_concorrentes": 1,
            "maiores_gaps": [],
            "guerra_de_precos": [],
            "historico": {"previous_run": "RUN_00", "mudancas": []},
            "series_temporais": self.series_temporais,
            "snapshots_observados": 15
        }

        self.memoria_stats = {
            "previous_run": "RUN_00",
            "novas_fontes": 1,
            "fontes_alteradas": 0,
            "eventos_delta": {
                "novos": [self.events[0]],
                "recorrentes": [self.events[1]],
                "expirados": [],
                "total_ativos": 2,
                "taxa_renovacao": 0.5
            }
        }

        self.pacote = {
            "resumo_executivo": ["Cenário com tendência de queda de preços no arroz."],
            "sinais": [
                {
                    "titulo": "Sinal de Expansão",
                    "tipo": "OPORTUNIDADE",
                    "impacto": "ALTO",
                    "urgencia": "MEDIA",
                    "evidence_ids": [1],
                    "acao": "Mapear concorrentes locais.",
                    "confianca": 0.9,
                    "limite": "30 dias",
                    "racional": "Nova loja aberta."
                }
            ],
            "concorrencia": [],
            "prioridades_30": ["Ação 1"],
            "prioridades_60": ["Ação 2"],
            "prioridades_90": ["Ação 3"],
            "lacunas": ["Nenhuma lacuna crítica."],
            "comparacao_precos": self.comparacao_precos,
            "memoria": self.memoria_stats
        }

    def tearDown(self):
        sniper.PASTA_EXECUCAO = self.original_pasta_exec
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_gerar_html_com_eventos_delta_e_series(self):
        """1. Valida que gerar_html renderiza resumo de novos/recorrentes, badges e tabela de séries temporais."""
        html = sniper.gerar_html(self.pacote, self.fontes, self.events, self.ambiente, self.memoria_stats)

        # Resumo de eventos
        self.assertIn("1 novos · 1 recorrentes", html)
        # Badges nos eventos
        self.assertIn("<span class='pill'>NOVO</span>", html)
        self.assertIn("<span class='pill'>RECORRENTE</span>", html)
        # Tabela de séries temporais
        self.assertIn("Séries Temporais e Tendências de Preços", html)
        self.assertIn("Arroz Parboilizado 5kg", html)
        self.assertIn("R$ 22.90", html)
        self.assertIn("-6.5%", html)
        self.assertIn("QUEDA", html)

    def test_02_gerar_html_fallback_vazio(self):
        """2. Valida fallback robusto de gerar_html quando memoria e series_temporais estão vazios."""
        html = sniper.gerar_html(
            {"comparacao_precos": {"enabled": False}},
            self.fontes,
            [{"kind": "EXPANSÃO", "title": "Loja 1", "importance": 70}],
            self.ambiente,
            {}
        )
        self.assertIsInstance(html, str)
        self.assertIn("Eventos canônicos", html)
        self.assertNotIn("Séries Temporais e Tendências de Preços", html)

    def test_03_comparar_precos_com_series_temporais(self):
        """3. Valida que comparar_precos() preenche a chave series_temporais a partir de MemoriaSniper."""
        db_file = self.temp_path / "test_comp_prices.sqlite3"
        mem = sniper.MemoriaSniper(db_file)

        snaps = [
            {"entity": "Carvalho", "role": "target", "source_domain": "carvalho.com.br", "product_key": "arroz_5kg", "product_name": "Arroz 5kg", "brand": "Marca", "unit": "5kg", "price": 20.0, "old_price": None, "promotion": 0, "url": "https://carvalho.com.br/1", "location_note": "Teresina"}
        ]
        mem.save_price_snapshots("RUN_01", snaps, captured_at="2026-08-01T08:00:00")
        mem.save_run("RUN_01", self.fontes, self.events, created_at="2026-08-01T08:00:00")

        res = sniper.comparar_precos(self.fontes, mem)
        self.assertIn("series_temporais", res)
        self.assertIsInstance(res["series_temporais"], dict)
        mem.conn.close()

    def test_04_inteligencia_json_payload_structure(self):
        """4. Valida que salvar_json salva pacote contendo eventos_delta e series_temporais sem erros."""
        caminho = sniper.salvar_json("inteligencia_teste.json", self.pacote)
        p = Path(caminho)
        self.assertTrue(p.exists())
        conteudo = p.read_text(encoding="utf-8")
        self.assertIn("series_temporais", conteudo)
        self.assertIn("eventos_delta", conteudo)
        self.assertIn("QUEDA", conteudo)

    def test_05_gerar_pdf_com_dados_temporais(self):
        """5. Valida que gerar_pdf executa normalmente na presença de pacotes com inteligência temporal."""
        pdf_path = sniper.gerar_pdf(self.pacote, self.fontes, self.events, self.ambiente, self.memoria_stats)
        if sniper.FPDF:
            self.assertIsNotNone(pdf_path)
            self.assertTrue(Path(pdf_path).exists())


if __name__ == "__main__":
    unittest.main()
