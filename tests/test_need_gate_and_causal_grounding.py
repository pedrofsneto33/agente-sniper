# -*- coding: utf-8 -*-
"""
Bateria de Testes Formais e Adversariais — Need Gate e Fundamentação Causal (Fase 55.1).
Valida o filtro conservador de soluções potenciais, explicabilidade da necessidade e salvaguardas contratuais.
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from domain.models import Fonte
from domain.profiles import obter_perfil_nicho
from domain.opportunities import (
    ActionableOpportunity,
    ScopeGovernance,
    avaliar_need_gate,
    formular_necessidade_e_fundamentacao,
    determinar_governanca_escopo,
    gerar_oportunidades_acionaveis,
    SCOPE_CONTRACTED_INTELLIGENCE,
    SCOPE_ANALYTICAL_RECOMMENDATION,
    SCOPE_POSSIBLE_SOLUTION,
    SOLUTION_SOFTWARE_CUSTOMIZADO,
    SOLUTION_PROCESSO_INTERNO,
    SOLUTION_CONSULTORIA_ADICIONAL,
    SOLUTION_INFRAESTRUTURA_INTEGRACAO,
    SOLUTION_OUTRO,
)
from domain.decision import inteligencia_deterministica
from reports.html import gerar_html
from reports.pdf import gerar_pdf


class TestNeedGateAndCausalGrounding(unittest.TestCase):
    """Suíte adversarial de testes para o Need Gate e explicabilidade causal."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.fontes = [
            Fonte(id=1, titulo="Inovação Digital Alpha", url="https://noticia.com/1", origem="web", score=85.0, confianca=0.95),
            Fonte(id=2, titulo="Expansão Regional Beta", url="https://noticia.com/2", origem="web", score=80.0, confianca=0.90),
            Fonte(id=3, titulo="Portal Digital Terceiro", url="https://noticia.com/3", origem="web", score=82.0, confianca=0.88),
        ]
        self.ambiente = {
            "score": 70, "label": "ALTA", "cobertura": 0.80,
            "dimensoes": {"EXPANSÃO": {"score": 80, "eventos": 1, "evidencias": 2, "eventos_correlacionados": 1}},
            "pressao_competitiva": {"score": 50, "label": "MÉDIA"},
            "vulnerabilidade_empresa": {"score": 15, "label": "BAIXA"},
            "momentum_mercado": 60,
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_evento_digital_isolado_sem_solucao(self):
        """1. Evento digital com 1 fonte e sem mudança material não gera SOFTWARE_CUSTOMIZADO."""
        ev = {
            "event_id": "ev_dig_1", "kind": "DIGITAL", "title": "Novo banner no site",
            "entity": "Alpha Concorrente", "confidence": 0.85, "importance": 70,
            "evidence_ids": [1], "independent_source_count": 1, "mudanca_material": False,
        }
        opps = gerar_oportunidades_acionaveis([ev], self.fontes)
        self.assertEqual(len(opps), 1)
        opp = opps[0]
        self.assertEqual(opp.governance.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(opp.governance.solution_type)
        self.assertIsNotNone(opp.recommended_action)
        self.assertIsNotNone(opp.identified_need)

    def test_02_evidencia_insuficiente_rejeita_solucao(self):
        """2. Confiança da evidência < 0.70 é rejeitada pelo Need Gate."""
        gov = avaliar_need_gate(
            kind="DIGITAL", action_type="TRANSFORMACAO_DIGITAL",
            evidence_confidence=0.65, independent_sources=3, relevance_score=80.0,
            is_material_change=True, target_entity="Alpha",
        )
        self.assertEqual(gov.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(gov.solution_type)

    def test_03_poucas_fontes_rejeita_solucao(self):
        """3. Menos de 2 fontes independentes é rejeitado pelo Need Gate."""
        gov = avaliar_need_gate(
            kind="DIGITAL", action_type="TRANSFORMACAO_DIGITAL",
            evidence_confidence=0.95, independent_sources=1, relevance_score=85.0,
            is_material_change=True, target_entity="Alpha",
        )
        self.assertEqual(gov.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(gov.solution_type)

    def test_04_baixa_relevancia_rejeita_solucao(self):
        """4. Relevância < 60.0 é rejeitada pelo Need Gate."""
        gov = avaliar_need_gate(
            kind="DIGITAL", action_type="TRANSFORMACAO_DIGITAL",
            evidence_confidence=0.95, independent_sources=2, relevance_score=55.0,
            is_material_change=True, target_entity="Alpha",
        )
        self.assertEqual(gov.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(gov.solution_type)

    def test_05_entidade_generica_rejeita_solucao(self):
        """5. Entidade genérica ('mercado', 'setor') é rejeitada pelo Need Gate."""
        gov = avaliar_need_gate(
            kind="EXPANSÃO", action_type="EXPANSAO_COMERCIAL",
            evidence_confidence=0.95, independent_sources=3, relevance_score=85.0,
            is_material_change=True, target_entity="mercado",
        )
        self.assertEqual(gov.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(gov.solution_type)

    def test_06_caso_suficientemente_fundamentado_aprova_solucao(self):
        """6. Dados robustos e fundamentados aprovam POSSIBLE_SOLUTION com salvaguardas."""
        ev = {
            "event_id": "ev_dig_ok", "kind": "DIGITAL", "title": "Lançamento de SuperApp e E-commerce Integrado",
            "entity": "Alpha Concorrente", "confidence": 0.92, "importance": 85,
            "evidence_ids": [1, 3], "independent_source_count": 2, "mudanca_material": True,
            "motivo_mudanca": "novo_canal_e_plataforma",
        }
        opps = gerar_oportunidades_acionaveis([ev], self.fontes)
        self.assertEqual(len(opps), 1)
        opp = opps[0]
        self.assertEqual(opp.governance.scope_type, SCOPE_POSSIBLE_SOLUTION)
        self.assertEqual(opp.governance.solution_type, SOLUTION_SOFTWARE_CUSTOMIZADO)
        self.assertFalse(opp.governance.in_contracted_scope)
        self.assertTrue(opp.governance.requires_separate_agreement)
        self.assertTrue(opp.governance.human_validation_required)
        self.assertIn("SuperApp", opp.title)
        self.assertIn("canais digitais", opp.identified_need)

    def test_07_recomendacao_analitica_permanece_ativa_sem_solucao(self):
        """7. Rejeição do Need Gate preserva fato, impacto, ação e necessidade."""
        ev = {
            "event_id": "ev_reg_1", "kind": "REGULAÇÃO", "title": "Nova Portaria Sanitária",
            "entity": "Órgão Fiscalizador", "confidence": 0.85, "importance": 80,
            "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": False,
        }
        opps = gerar_oportunidades_acionaveis([ev], self.fontes)
        self.assertEqual(len(opps), 1)
        opp = opps[0]
        self.assertEqual(opp.governance.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(opp.governance.solution_type)
        self.assertIn("Nova Portaria", opp.underlying_fact)
        self.assertIn("Auditoria de conformidade", opp.identified_need)
        self.assertIn("Validar o teor da norma", opp.recommended_action)

    def test_08_anti_promessa_em_todos_os_textos_e_disclaimers(self):
        """8. Garante ausência de termos que impliquem compromisso de execução técnica."""
        for kind in ["EXPANSÃO", "PARCERIA", "PRODUTO/SERVIÇO", "DIGITAL", "REGULAÇÃO", "PREÇO"]:
            need, rat = formular_necessidade_e_fundamentacao(kind, "Evento X", "Empresa Y", "Setor Z", 2, 80.0)
            gov = avaliar_need_gate(kind, "TRANSFORMACAO_DIGITAL", 0.9, 2, 80.0, True, "Empresa Y")
            for text in [need, rat, gov.disclaimer]:
                t_lower = text.lower()
                self.assertNotIn("iremos implementar", t_lower)
                self.assertNotIn("será desenvolvido", t_lower)
                self.assertNotIn("nossa equipe fará", t_lower)
                self.assertNotIn("vamos implantar", t_lower)

    def test_09_multi_nicho_independente_need_gate(self):
        """9. Need Gate opera identicamente em perfis de supermercado, advocacia, clínica e farmácia."""
        ev = {
            "event_id": "ev_exp", "kind": "EXPANSÃO", "title": "Inauguração Nova Filial",
            "entity": "Rede Delta", "confidence": 0.90, "importance": 80,
            "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True,
        }
        perfis = [
            obter_perfil_nicho("supermercado"),
            {"label": "Advocacia", "relevance_weights": {"EXPANSÃO": 0.85}},
            {"label": "Clínica", "relevance_weights": {"EXPANSÃO": 0.80}},
            {"label": "Farmácia", "relevance_weights": {"EXPANSÃO": 0.90}},
            {"label": "Imobiliária", "relevance_weights": {"EXPANSÃO": 0.88}},
        ]
        for p in perfis:
            opps = gerar_oportunidades_acionaveis([ev], self.fontes, profile=p)
            self.assertEqual(len(opps), 1)
            self.assertEqual(opps[0].governance.scope_type, SCOPE_POSSIBLE_SOLUTION)
            self.assertEqual(opps[0].governance.solution_type, SOLUTION_INFRAESTRUTURA_INTEGRACAO)

    def test_10_renderizacao_html_e_pdf_com_need_e_rationale(self):
        """10. HTML e PDF renderizam os campos de explicabilidade causal."""
        eventos = [{
            "event_id": "e1", "kind": "DIGITAL", "title": "Portal de Clientes",
            "entity": "Alpha", "confidence": 0.92, "importance": 85,
            "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True,
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("Necessidade/Lacuna:", html)
        self.assertIn("Fundamentação:", html)

        pdf_path = gerar_pdf(pacote, self.fontes, eventos, self.ambiente, {}, pasta_execucao=self.temp_path, run_id="pdf_need_test")
        self.assertIsNotNone(pdf_path)
        self.assertTrue(Path(pdf_path).exists())


if __name__ == "__main__":
    unittest.main()
