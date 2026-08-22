# -*- coding: utf-8 -*-
"""
Bateria de Testes Formais e Adversariais — Tendência Temporal Longitudinal (Fase 58.1).
Valida a classificação determinística dos 5 estados de temporal_trend:
INEDITO, ACELERANDO, ESTABILIZADO, MARCO_CONCLUIDO, REATIVADO.
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from domain.models import Fonte
from domain.deltas import (
    determinar_tendencia_temporal,
    TEMPORAL_TREND_INEDITO,
    TEMPORAL_TREND_ACELERANDO,
    TEMPORAL_TREND_ESTABILIZADO,
    TEMPORAL_TREND_MARCO_CONCLUIDO,
    TEMPORAL_TREND_REATIVADO,
    ESTADO_EVENTO_NOVO,
    ESTADO_EVENTO_ATUALIZADO,
    ESTADO_EVENTO_CONTINUIDADE,
    ESTADO_EVENTO_SEM_MUDANCA,
)
from domain.opportunities import (
    ActionableOpportunity,
    gerar_oportunidades_acionaveis,
    consolidar_oportunidades_tematicas,
    selecionar_oportunidades_executivas,
)
from domain.decision import inteligencia_deterministica
from reports.html import gerar_html
from reports.pdf import gerar_pdf


class TestTemporalTrend(unittest.TestCase):
    """Suíte adversarial para a classificação longitudinal de temporal_trend."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.fontes = [
            Fonte(id=1, titulo="Alpha Anuncia Nova Filial", url="https://noticia.com/1", origem="web", score=85.0, confianca=0.90),
            Fonte(id=2, titulo="Alpha Inicia Obras da Filial", url="https://noticia.com/2", origem="web", score=88.0, confianca=0.92),
            Fonte(id=3, titulo="Alpha Inaugura Filial Centro", url="https://noticia.com/3", origem="web", score=95.0, confianca=0.95),
        ]
        self.ambiente = {
            "score": 75, "label": "ALTA", "cobertura": 0.85,
            "dimensoes": {"EXPANSÃO": {"score": 85, "eventos": 1, "evidencias": 2, "eventos_correlacionados": 1}},
            "pressao_competitiva": {"score": 50, "label": "MÉDIA"},
            "vulnerabilidade_empresa": {"score": 15, "label": "BAIXA"},
            "momentum_mercado": 60,
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_fato_inedito_classificado_como_inedito(self):
        """1. Evento novo sem histórico é classificado como INEDITO."""
        trend = determinar_tendencia_temporal(
            estado_incremental=ESTADO_EVENTO_NOVO,
            motivo_mudanca="fato_inedito",
            is_material=True,
            entregue_anteriormente=False,
        )
        self.assertEqual(trend, TEMPORAL_TREND_INEDITO)

    def test_02_aceleracao_por_novas_fontes_classificada_como_acelerando(self):
        """2. Evento atualizado com novas fontes independentes é classificado como ACELERANDO."""
        trend = determinar_tendencia_temporal(
            estado_incremental=ESTADO_EVENTO_ATUALIZADO,
            motivo_mudanca="nova_corroboracao: 1 -> 3 fontes",
            is_material=True,
            entregue_anteriormente=False,
        )
        self.assertEqual(trend, TEMPORAL_TREND_ACELERANDO)

    def test_03_estabilizacao_sem_mudanca_classificada_como_estabilizado(self):
        """3. Evento em continuidade ou sem mudança material é classificado como ESTABILIZADO."""
        trend_cont = determinar_tendencia_temporal(
            estado_incremental=ESTADO_EVENTO_CONTINUIDADE,
            motivo_mudanca="sem_mudanca_material",
            is_material=False,
            entregue_anteriormente=True,
            continuity_cycles=2,
        )
        self.assertEqual(trend_cont, TEMPORAL_TREND_ESTABILIZADO)

        trend_sem = determinar_tendencia_temporal(
            estado_incremental=ESTADO_EVENTO_SEM_MUDANCA,
            motivo_mudanca="sem_mudanca_material",
            is_material=False,
            entregue_anteriormente=True,
        )
        self.assertEqual(trend_sem, TEMPORAL_TREND_ESTABILIZADO)

    def test_04_marco_concluido_classificado_como_marco_concluido(self):
        """4. Evento com desfecho (inauguração, conclusão, contratação) é classificado como MARCO_CONCLUIDO."""
        trend = determinar_tendencia_temporal(
            estado_incremental=ESTADO_EVENTO_ATUALIZADO,
            motivo_mudanca="evolucao_fato: anuncia -> inaugura",
            is_material=True,
            entregue_anteriormente=True,
            title="Alpha Inaugura Loja Centro",
        )
        self.assertEqual(trend, TEMPORAL_TREND_MARCO_CONCLUIDO)

    def test_05_reativacao_apos_silencio_classificada_como_reativado(self):
        """5. Evento já entregue anteriormente que volta a ter alteração material factual é classificado como REATIVADO."""
        trend = determinar_tendencia_temporal(
            estado_incremental=ESTADO_EVENTO_ATUALIZADO,
            motivo_mudanca="nova_corroboracao: 2 novas fontes",
            is_material=True,
            entregue_anteriormente=True,
            continuity_cycles=2,
        )
        self.assertEqual(trend, TEMPORAL_TREND_REATIVADO)

    def test_06_continuidade_nao_confundida_com_aceleracao(self):
        """6. Persistência de fato com continuidade não pode ser rotulada como ACELERANDO."""
        trend = determinar_tendencia_temporal(
            estado_incremental=ESTADO_EVENTO_CONTINUIDADE,
            motivo_mudanca="sem_mudanca_material",
            is_material=False,
            entregue_anteriormente=True,
        )
        self.assertNotEqual(trend, TEMPORAL_TREND_ACELERANDO)
        self.assertEqual(trend, TEMPORAL_TREND_ESTABILIZADO)

    def test_07_republicacao_sem_materialidade_nao_e_inedito(self):
        """7. Republicação de fonte antiga sem mudança material não é INEDITO nem ACELERANDO."""
        trend = determinar_tendencia_temporal(
            estado_incremental=ESTADO_EVENTO_SEM_MUDANCA,
            motivo_mudanca="sem_mudanca_material",
            is_material=False,
            entregue_anteriormente=True,
        )
        self.assertEqual(trend, TEMPORAL_TREND_ESTABILIZADO)

    def test_08_conclusao_nao_confundida_com_simples_aceleracao(self):
        """8. Inauguração concluída tem precedência como MARCO_CONCLUIDO sobre ACELERANDO."""
        trend = determinar_tendencia_temporal(
            estado_incremental=ESTADO_EVENTO_ATUALIZADO,
            motivo_mudanca="evolucao_fato: obras -> inaugura",
            is_material=True,
            title="Alpha Inaugura Centro",
        )
        self.assertEqual(trend, TEMPORAL_TREND_MARCO_CONCLUIDO)

    def test_09_geracao_oportunidades_com_temporal_trend(self):
        """9. gerar_oportunidades_acionaveis preenche temporal_trend no objeto ActionableOpportunity."""
        ev = {
            "event_id": "e1", "kind": "EXPANSÃO", "title": "Loja Nova Alpha", "entity": "Alpha",
            "confidence": 0.90, "importance": 85, "evidence_ids": [1], "independent_source_count": 1,
            "mudanca_material": True, "motivo_mudanca": "fato_inedito", "estado_incremental": ESTADO_EVENTO_NOVO
        }
        opps = gerar_oportunidades_acionaveis([ev], self.fontes)
        self.assertEqual(len(opps), 1)
        self.assertEqual(opps[0].temporal_trend, TEMPORAL_TREND_INEDITO)
        self.assertEqual(opps[0].to_dict()["temporal_trend"], TEMPORAL_TREND_INEDITO)

    def test_10_consolidacao_preserva_tendencia_mais_forte(self):
        """10. Consolidação preserva a tendência de maior relevância temporal (MARCO_CONCLUIDO > ACELERANDO > INEDITO)."""
        opp1 = ActionableOpportunity(
            id="o1", event_id="e1", category="OPORTUNIDADE", action_type="EXPANSAO_COMERCIAL",
            title="Alpha Loja", underlying_fact="Alpha Loja", detected_change="",
            contextual_impact="Imp", recommended_action="Ac", contact_suggestion=None,
            target_entity="Alpha", evidence_ids=(1,), evidence_confidence=0.9,
            opportunity_confidence=0.8, relevance_score=80.0, should_deliver=True,
            delivery_fingerprint="fp1", identified_need="Expansao", need_rationale="Rat",
            intelligence_priority=75.0, temporal_trend=TEMPORAL_TREND_ACELERANDO
        )
        opp2 = ActionableOpportunity(
            id="o2", event_id="e2", category="OPORTUNIDADE", action_type="EXPANSAO_COMERCIAL",
            title="Alpha Loja", underlying_fact="Alpha Loja", detected_change="",
            contextual_impact="Imp", recommended_action="Ac", contact_suggestion=None,
            target_entity="Alpha", evidence_ids=(2,), evidence_confidence=0.95,
            opportunity_confidence=0.85, relevance_score=85.0, should_deliver=True,
            delivery_fingerprint="fp2", identified_need="Expansao", need_rationale="Rat",
            intelligence_priority=85.0, temporal_trend=TEMPORAL_TREND_MARCO_CONCLUIDO
        )
        cons = consolidar_oportunidades_tematicas([opp1, opp2])
        self.assertEqual(len(cons), 1)
        self.assertEqual(cons[0].temporal_trend, TEMPORAL_TREND_MARCO_CONCLUIDO)

    def test_11_renderizacao_html_e_pdf_com_temporal_trend(self):
        """11. HTML e PDF renderizam o temporal_trend nos cards com a mesma classificação."""
        eventos = [{
            "event_id": "e1", "kind": "EXPANSÃO", "title": "Alpha Inaugura Loja Centro", "entity": "Alpha",
            "confidence": 0.95, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2,
            "mudanca_material": True, "motivo_mudanca": "evolucao_fato: planeja -> inaugura", "estado_incremental": ESTADO_EVENTO_ATUALIZADO
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        self.assertEqual(pacote["oportunidades"][0]["temporal_trend"], TEMPORAL_TREND_MARCO_CONCLUIDO)

        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("MARCO CONCLUIDO", html)

        pdf_path = gerar_pdf(pacote, self.fontes, eventos, self.ambiente, {}, pasta_execucao=self.temp_path, run_id="pdf_trend_test")
        self.assertIsNotNone(pdf_path)
        self.assertTrue(Path(pdf_path).exists())


if __name__ == "__main__":
    unittest.main()
