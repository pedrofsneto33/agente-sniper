# -*- coding: utf-8 -*-
"""
Testes Unitários de Scoring e Métricas — Agente Sniper v11.8.1
Cobre: score_clamp, medir_dimensoes, score_ambiente_competitivo,
score_pressao_competitiva, score_vulnerabilidade_empresa, score_momentum.
"""
import sys
import unittest
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import agente_sniper_v11_8 as sniper


class TestScoring(unittest.TestCase):

    def setUp(self):
        self.empresa = sniper.EMPRESA_ALVO

    def test_01_score_clamp_limites(self):
        """Testa restrição numérica entre 0 e 100 com arredondamento."""
        self.assertEqual(sniper.score_clamp(-100), 0)
        self.assertEqual(sniper.score_clamp(-0.01), 0)
        self.assertEqual(sniper.score_clamp(0.0), 0)
        self.assertEqual(sniper.score_clamp(50.4), 50)
        self.assertEqual(sniper.score_clamp(50.6), 51)
        self.assertEqual(sniper.score_clamp(100.0), 100)
        self.assertEqual(sniper.score_clamp(999.9), 100)

    def test_02_medir_dimensoes_entrada_vazia(self):
        """Testa medição com listas vazias para todas as 10 dimensões canônicas."""
        dimensoes = sniper.medir_dimensoes([], [])
        self.assertIsInstance(dimensoes, dict)
        dimensoes_esperadas = {
            "PREÇO", "REPUTAÇÃO", "ATENDIMENTO", "EXPANSÃO", "DIGITAL",
            "MARKETING", "PESSOAS", "REGULAÇÃO", "PRODUTO/SERVIÇO", "PARCERIA"
        }
        for d in dimensoes_esperadas:
            self.assertIn(d, dimensoes)
            self.assertEqual(dimensoes[d]["score"], 0)
            self.assertEqual(dimensoes[d]["eventos"], 0)

    def test_03_medir_dimensoes_com_fontes_e_eventos(self):
        """Testa cálculo de dimensões com fontes sintéticas e eventos."""
        f1 = sniper.Fonte(
            id=1, titulo="Carvalho Super abre filial", url="https://teste.com/loja",
            origem="web", conteudo="Expansão e novas unidades em Teresina",
            data_publicacao="2026-08-15", alias_empresa=self.empresa,
            cidade_confirmada=True, estado_confirmado=True, escopo="local",
            entidade=self.empresa, score=85.0
        )
        events = [{
            "event_id": "EVT_01", "kind": "EXPANSÃO", "title": "Abertura de Filial",
            "importance": 80, "evidence_ids": [1], "confidence": 0.9,
            "entity": self.empresa, "current": True
        }]
        dimensoes = sniper.medir_dimensoes([f1], events)
        self.assertGreater(dimensoes["EXPANSÃO"]["score"], 0)

    def test_04_score_ambiente_competitivo_escala(self):
        """Testa score de atividade interna da empresa com dimensões vazias e preenchidas."""
        dimensoes_vazias = sniper.medir_dimensoes([], [])
        res_vazio = sniper.score_ambiente_competitivo(dimensoes_vazias)
        self.assertEqual(res_vazio["score"], 0)
        self.assertEqual(res_vazio["label"], "BAIXA")

        # Mock de dimensões com atividade moderada usando as chaves canônicas com acento
        dimensoes_ativas = {k: {"score": 60, "status": "ATIVO"} for k in [
            "PREÇO", "EXPANSÃO", "DIGITAL", "MARKETING", "PRODUTO/SERVIÇO",
            "PARCERIA", "REPUTAÇÃO", "ATENDIMENTO", "REGULAÇÃO", "PESSOAS"
        ]}
        res_ativo = sniper.score_ambiente_competitivo(dimensoes_ativas)
        self.assertGreaterEqual(res_ativo["score"], 45)
        self.assertIn(res_ativo["label"], ["MÉDIA", "ALTA"])

    def test_05_score_pressao_competitiva_concorrentes(self):
        """Testa score de pressão de concorrentes externos."""
        # Sem concorrentes -> score é None
        res_sem_externos = sniper.score_pressao_competitiva([], [])
        self.assertIsNone(res_sem_externos["score"])
        self.assertEqual(res_sem_externos["label"], "NÃO CALCULADO")

        # Com eventos de múltiplos concorrentes externos
        eventos_concorrentes = [
            {"event_id": "C1", "entity": "Mateus", "importance": 75, "confidence": 0.85, "current": True, "independent_source_count": 2},
            {"event_id": "C2", "entity": "Assai", "importance": 70, "confidence": 0.80, "current": True, "independent_source_count": 2},
            {"event_id": "C3", "entity": "Atacadao", "importance": 65, "confidence": 0.80, "current": True, "independent_source_count": 1}
        ]
        res_pressao = sniper.score_pressao_competitiva([], eventos_concorrentes)
        self.assertIsNotNone(res_pressao["score"])
        self.assertGreaterEqual(res_pressao["score"], 40)
        self.assertIn("Mateus", res_pressao["entidades"])

    def test_06_score_vulnerabilidade_empresa_casos_limite(self):
        """Testa vulnerabilidade contra inflação artificial e cálculo com eventos de risco reais."""
        # Sem eventos de risco -> score zero
        res_zero = sniper.score_vulnerabilidade_empresa([])
        self.assertEqual(res_zero["score"], 0)
        self.assertEqual(res_zero["label"], "BAIXA")

        # Evento de risco único sem corroboração -> deve ser limitado a no máximo 38/100
        evento_isolado = [{
            "event_id": "RISK_01", "entity": self.empresa, "kind": "REPUTAÇÃO",
            "importance": 90, "confidence": 0.90, "current": True,
            "independent_source_count": 1, "date": "2026-08-10"
        }]
        res_isolado = sniper.score_vulnerabilidade_empresa(evento_isolado)
        self.assertLessEqual(res_isolado["score"], 38)
        self.assertEqual(res_isolado["label"], "BAIXA")

        # Múltiplos eventos de risco corroborados com 2+ fontes nas categorias de risco reais
        eventos_graves = [
            {"event_id": "R1", "entity": self.empresa, "kind": "REPUTAÇÃO", "importance": 85, "confidence": 0.9, "current": True, "independent_source_count": 3, "date": "2026-08-10"},
            {"event_id": "R2", "entity": self.empresa, "kind": "REGULAÇÃO", "importance": 80, "confidence": 0.9, "current": True, "independent_source_count": 2, "date": "2026-08-12"},
            {"event_id": "R3", "entity": self.empresa, "kind": "ATENDIMENTO", "importance": 75, "confidence": 0.85, "current": True, "independent_source_count": 2, "date": "2026-08-14"}
        ]
        res_grave = sniper.score_vulnerabilidade_empresa(eventos_graves)
        self.assertGreaterEqual(res_grave["score"], 50)

    def test_07_score_momentum_recencia(self):
        """Testa momentum de mercado baseado na recência ponderada."""
        self.assertEqual(sniper.score_momentum([], []), 0)

        f = sniper.Fonte(id=1, titulo="Noticia recente", url="https://u.com", origem="web", data_publicacao="2026-08-17", score=80.0)
        events = [{"event_id": "E1", "date": "2026-08-17", "current": True, "importance": 80, "evidence_ids": [1]}]
        mom = sniper.score_momentum(events, [f])
        self.assertIsInstance(mom, int)
        self.assertGreaterEqual(mom, 0)
        self.assertLessEqual(mom, 100)

    def test_08_determinismo_estrito_de_scores(self):
        """Garante que chamadas repetidas com os mesmos dados produzem resultados idênticos."""
        dimensoes = sniper.medir_dimensoes([], [])
        res1 = sniper.score_ambiente_competitivo(dimensoes)
        res2 = sniper.score_ambiente_competitivo(dimensoes)
        self.assertEqual(res1, res2)


if __name__ == "__main__":
    unittest.main()
