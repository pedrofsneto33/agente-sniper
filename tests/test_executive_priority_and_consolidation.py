# -*- coding: utf-8 -*-
"""
Bateria de Testes Formais e Adversariais — Priorização Executiva e Consolidação Temática (Fase 56.1).
Valida os 25 requisitos de monotonicidade de prioridade, consolidação semântica, seleção por diversidade e governança.
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
    calcular_prioridade_inteligencia,
    consolidar_oportunidades_tematicas,
    selecionar_oportunidades_executivas,
    gerar_oportunidades_acionaveis,
    avaliar_need_gate,
    SCOPE_CONTRACTED_INTELLIGENCE,
    SCOPE_ANALYTICAL_RECOMMENDATION,
    SCOPE_POSSIBLE_SOLUTION,
    SOLUTION_SOFTWARE_CUSTOMIZADO,
    SOLUTION_INFRAESTRUTURA_INTEGRACAO,
    SOLUTION_CONSULTORIA_ADICIONAL,
)
from domain.decision import inteligencia_deterministica
from reports.html import gerar_html
from reports.pdf import gerar_pdf


class TestExecutivePriorityAndConsolidation(unittest.TestCase):
    """Suíte adversarial para priorização executiva, consolidação de redundâncias e seleção com diversidade."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.fontes = [
            Fonte(id=1, titulo="Inovação Digital Alpha", url="https://noticia.com/1", origem="web", score=85.0, confianca=0.95),
            Fonte(id=2, titulo="Expansão Regional Beta", url="https://noticia.com/2", origem="web", score=80.0, confianca=0.90),
            Fonte(id=3, titulo="Preços Gamma", url="https://noticia.com/3", origem="web", score=78.0, confianca=0.88),
            Fonte(id=4, titulo="Expansão Alpha Bairro Sul", url="https://noticia.com/4", origem="web", score=82.0, confianca=0.92),
            Fonte(id=5, titulo="Expansão Alpha Bairro Norte", url="https://noticia.com/5", origem="web", score=81.0, confianca=0.91),
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

    # -------------------------------------------------------------
    # ETAPA 1: TESTES DE PRIORIDADE DE INTELIGÊNCIA (1 a 9)
    # -------------------------------------------------------------
    def test_01_relevancia_maior_aumenta_ou_mantem_prioridade(self):
        """1. Aumentar relevance_score nunca diminui intelligence_priority (monotonicidade)."""
        p1 = calcular_prioridade_inteligencia(relevance_score=50.0, opportunity_confidence=0.8, is_material=False, independent_sources=2)
        p2 = calcular_prioridade_inteligencia(relevance_score=80.0, opportunity_confidence=0.8, is_material=False, independent_sources=2)
        self.assertGreater(p2, p1)

    def test_02_confianca_maior_aumenta_ou_mantem_prioridade(self):
        """2. Aumentar opportunity_confidence nunca diminui intelligence_priority."""
        p1 = calcular_prioridade_inteligencia(relevance_score=70.0, opportunity_confidence=0.5, is_material=False, independent_sources=2)
        p2 = calcular_prioridade_inteligencia(relevance_score=70.0, opportunity_confidence=0.9, is_material=False, independent_sources=2)
        self.assertGreater(p2, p1)

    def test_03_materialidade_verdadeira_adiciona_prioridade(self):
        """3. is_material=True gera prioridade estritamente superior a is_material=False."""
        p_sem_mat = calcular_prioridade_inteligencia(relevance_score=70.0, opportunity_confidence=0.8, is_material=False, independent_sources=2)
        p_com_mat = calcular_prioridade_inteligencia(relevance_score=70.0, opportunity_confidence=0.8, is_material=True, independent_sources=2)
        self.assertEqual(round(p_com_mat - p_sem_mat, 2), 20.0)

    def test_04_mais_fontes_independentes_aumenta_prioridade(self):
        """4. Mais fontes independentes incrementa o bônus de corroboração até o limite."""
        p1 = calcular_prioridade_inteligencia(relevance_score=70.0, opportunity_confidence=0.8, is_material=False, independent_sources=1)
        p2 = calcular_prioridade_inteligencia(relevance_score=70.0, opportunity_confidence=0.8, is_material=False, independent_sources=2)
        p3 = calcular_prioridade_inteligencia(relevance_score=70.0, opportunity_confidence=0.8, is_material=False, independent_sources=3)
        self.assertGreater(p2, p1)
        self.assertGreater(p3, p2)

    def test_05_intervalo_estrito_zero_a_cem(self):
        """5. A prioridade está rigorosamente contida no intervalo [0.0, 100.0]."""
        p_min = calcular_prioridade_inteligencia(relevance_score=-10.0, opportunity_confidence=-0.5, is_material=False, independent_sources=0)
        p_max = calcular_prioridade_inteligencia(relevance_score=150.0, opportunity_confidence=1.5, is_material=True, independent_sources=10)
        self.assertEqual(p_min, 0.0)
        self.assertEqual(p_max, 100.0)

    def test_06_determinismo_absoluto_prioridade(self):
        """6. Mesma entrada produz exatamente a mesma prioridade."""
        p_a = calcular_prioridade_inteligencia(75.5, 0.85, True, 3)
        p_b = calcular_prioridade_inteligencia(75.5, 0.85, True, 3)
        self.assertEqual(p_a, p_b)

    def test_07_resiliencia_a_valores_limites(self):
        """7. Trata valores nulos ou vazios de forma segura e determinística."""
        p = calcular_prioridade_inteligencia(0, 0, False, 1)
        self.assertEqual(p, 0.0)

    def test_08_prioridade_nao_altera_relevance_score(self):
        """8. Cálculo de prioridade não altera o relevance_score original da oportunidade."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja Nova", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2], "mudanca_material": True}
        opp = gerar_oportunidades_acionaveis([ev], self.fontes)[0]
        self.assertEqual(opp.relevance_score, 64.6)
        self.assertGreater(opp.intelligence_priority, 0.0)

    def test_09_prioridade_nao_altera_opportunity_confidence(self):
        """9. Cálculo de prioridade não altera a opportunity_confidence."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja Nova", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2], "mudanca_material": True}
        opp = gerar_oportunidades_acionaveis([ev], self.fontes)[0]
        self.assertEqual(opp.opportunity_confidence, 0.765)

    # -------------------------------------------------------------
    # ETAPA 2: TESTES DE CONSOLIDAÇÃO TEMÁTICA (10 a 16)
    # -------------------------------------------------------------
    def test_10_tres_oportunidades_iguais_mesma_entidade_consolidam_em_uma(self):
        """10. Três eventos de expansão da mesma entidade consolidam em 1 oportunidade síntese."""
        ev1 = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Alpha Unidade Centro", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1], "independent_source_count": 1}
        ev2 = {"event_id": "e2", "kind": "EXPANSÃO", "title": "Alpha Unidade Sul", "entity": "Alpha", "confidence": 0.92, "importance": 85, "evidence_ids": [4], "independent_source_count": 1}
        ev3 = {"event_id": "e3", "kind": "EXPANSÃO", "title": "Alpha Unidade Norte", "entity": "Alpha", "confidence": 0.91, "importance": 82, "evidence_ids": [5], "independent_source_count": 1}
        opps = gerar_oportunidades_acionaveis([ev1, ev2, ev3], self.fontes)
        self.assertEqual(len(opps), 3)

        consolidadas = consolidar_oportunidades_tematicas(opps)
        self.assertEqual(len(consolidadas), 1)
        self.assertEqual(consolidadas[0].metadata.get("consolidated_count"), 3)

    def test_11_evidence_ids_unidos_sem_duplicacao(self):
        """11. Consolidação agrega evidence_ids sem duplicações em tupla ordenada."""
        ev1 = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja 1", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}
        ev2 = {"event_id": "e2", "kind": "EXPANSÃO", "title": "Loja 2", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [2, 4]}
        opps = gerar_oportunidades_acionaveis([ev1, ev2], self.fontes)
        cons = consolidar_oportunidades_tematicas(opps)
        self.assertEqual(cons[0].evidence_ids, (1, 2, 4))

    def test_12_oportunidades_de_entidades_diferentes_nao_sao_fundidas(self):
        """12. Oportunidades de entidades distintas permanecem estritamente separadas."""
        ev_alpha = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Alpha Expansão", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1]}
        ev_beta = {"event_id": "e2", "kind": "EXPANSÃO", "title": "Beta Expansão", "entity": "Beta", "confidence": 0.9, "importance": 80, "evidence_ids": [2]}
        opps = gerar_oportunidades_acionaveis([ev_alpha, ev_beta], self.fontes)
        cons = consolidar_oportunidades_tematicas(opps)
        self.assertEqual(len(cons), 2)
        entidades = {c.target_entity for c in cons}
        self.assertEqual(entidades, {"Alpha", "Beta"})

    def test_13_mesma_entidade_necessidades_diferentes_permanecem_separadas(self):
        """13. Mesma entidade em dimensões diferentes (EXPANSÃO vs DIGITAL) não são fundidas."""
        ev_exp = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Alpha Loja", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1]}
        ev_dig = {"event_id": "e2", "kind": "DIGITAL", "title": "Alpha E-commerce", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1]}
        opps = gerar_oportunidades_acionaveis([ev_exp, ev_dig], self.fontes)
        cons = consolidar_oportunidades_tematicas(opps)
        self.assertEqual(len(cons), 2)

    def test_14_mesma_entidade_action_type_diferente_permanece_separado(self):
        """14. Mesma entidade com action_type diferente não são unificados."""
        ev1 = {"event_id": "e1", "kind": "PARCERIA", "title": "Alpha Joint Venture", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1]}
        ev2 = {"event_id": "e2", "kind": "PRODUTO/SERVIÇO", "title": "Alpha Novo Produto", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1]}
        opps = gerar_oportunidades_acionaveis([ev1, ev2], self.fontes)
        cons = consolidar_oportunidades_tematicas(opps)
        self.assertEqual(len(cons), 2)

    def test_15_consolidacao_rigorosamente_deterministica(self):
        """15. Múltiplas execuções de consolidação produzem ordem e conteúdo idênticos."""
        ev1 = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Alpha 1", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1]}
        ev2 = {"event_id": "e2", "kind": "EXPANSÃO", "title": "Alpha 2", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [4]}
        opps = gerar_oportunidades_acionaveis([ev1, ev2], self.fontes)
        c1 = consolidar_oportunidades_tematicas(opps)
        c2 = consolidar_oportunidades_tematicas(opps)
        self.assertEqual(c1[0].id, c2[0].id)
        self.assertEqual(c1[0].evidence_ids, c2[0].evidence_ids)

    def test_16_nenhuma_evidencia_nova_inventada(self):
        """16. A lista de evidence_ids consolidada contém estritamente evidências originais."""
        ev1 = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Alpha 1", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1]}
        ev2 = {"event_id": "e2", "kind": "EXPANSÃO", "title": "Alpha 2", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [5]}
        opps = gerar_oportunidades_acionaveis([ev1, ev2], self.fontes)
        cons = consolidar_oportunidades_tematicas(opps)
        self.assertEqual(set(cons[0].evidence_ids), {1, 5})

    # -------------------------------------------------------------
    # ETAPA 3: TESTES DE SELEÇÃO EXECUTIVA E DIVERSIDADE (17 a 20)
    # -------------------------------------------------------------
    def test_17_diversidade_de_entidades_na_grade_executiva(self):
        """17. Dez eventos de Alpha + 2 de Beta e Gamma não permitem que Alpha domine todos os 8 slots."""
        eventos = [
            {"event_id": f"a{i}", "kind": "EXPANSÃO", "title": f"Alpha Loja {i}", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1], "independent_source_count": 2, "mudanca_material": True}
            for i in range(10)
        ]
        eventos.append({"event_id": "b1", "kind": "EXPANSÃO", "title": "Beta Loja 1", "entity": "Beta", "confidence": 0.90, "importance": 85, "evidence_ids": [2], "independent_source_count": 2, "mudanca_material": True})
        eventos.append({"event_id": "g1", "kind": "DIGITAL", "title": "Gamma App", "entity": "Gamma", "confidence": 0.90, "importance": 85, "evidence_ids": [3], "independent_source_count": 2, "mudanca_material": True})

        opps = gerar_oportunidades_acionaveis(eventos, self.fontes)
        exec_sel = selecionar_oportunidades_executivas(opps, limite=8)

        # Alpha foi consolidada em 1 card, e Beta e Gamma foram incluídas
        entidades_sel = [o.target_entity for o in exec_sel]
        self.assertIn("Beta", entidades_sel)
        self.assertIn("Gamma", entidades_sel)
        self.assertIn("Alpha", entidades_sel)

    def test_18_duas_oportunidades_distintas_da_mesma_entidade_podem_coexistir(self):
        """18. Duas oportunidades legítimas e distintas (EXPANSÃO e DIGITAL) da mesma entidade podem coexistir."""
        ev1 = {"event_id": "a1", "kind": "EXPANSÃO", "title": "Alpha Nova Loja", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1], "independent_source_count": 2, "mudanca_material": True}
        ev2 = {"event_id": "a2", "kind": "DIGITAL", "title": "Alpha Novo App", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1], "independent_source_count": 2, "mudanca_material": True}
        ev3 = {"event_id": "b1", "kind": "EXPANSÃO", "title": "Beta Nova Loja", "entity": "Beta", "confidence": 0.90, "importance": 85, "evidence_ids": [2], "independent_source_count": 2, "mudanca_material": True}

        opps = gerar_oportunidades_acionaveis([ev1, ev2, ev3], self.fontes)
        exec_sel = selecionar_oportunidades_executivas(opps, limite=8)
        self.assertEqual(len(exec_sel), 3)

    def test_19_materialidade_alta_eleva_prioridade_na_selecao(self):
        """19. Oportunidade com mudança material possui prioridade superior a evento estático."""
        ev_estatico = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja Antiga", "entity": "Alpha", "confidence": 0.90, "importance": 80, "evidence_ids": [1], "mudanca_material": False}
        ev_material = {"event_id": "e2", "kind": "EXPANSÃO", "title": "Nova Inauguração", "entity": "Beta", "confidence": 0.90, "importance": 80, "evidence_ids": [2], "mudanca_material": True}
        opps = gerar_oportunidades_acionaveis([ev_estatico, ev_material], self.fontes)
        exec_sel = selecionar_oportunidades_executivas(opps, limite=8)
        self.assertEqual(exec_sel[0].target_entity, "Beta")

    def test_20_desempate_deterministico(self):
        """20. Empate em todos os scores possui desempate determinístico por ID."""
        ev1 = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja A", "entity": "Empresa A", "confidence": 0.90, "importance": 80, "evidence_ids": [1]}
        ev2 = {"event_id": "e2", "kind": "EXPANSÃO", "title": "Loja B", "entity": "Empresa B", "confidence": 0.90, "importance": 80, "evidence_ids": [2]}
        opps1 = gerar_oportunidades_acionaveis([ev1, ev2], self.fontes)
        opps2 = gerar_oportunidades_acionaveis([ev1, ev2], self.fontes)
        s1 = selecionar_oportunidades_executivas(opps1, limite=8)
        s2 = selecionar_oportunidades_executivas(opps2, limite=8)
        self.assertEqual([x.id for x in s1], [x.id for x in s2])

    # -------------------------------------------------------------
    # ETAPA 4: GOVERNANÇA E INTEGRAÇÃO DE RELATÓRIOS (21 a 25)
    # -------------------------------------------------------------
    def test_21_consolidacao_preserva_scope_governance(self):
        """21. Consolidação não corrompe metadados de ScopeGovernance."""
        ev1 = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja 1", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True}
        ev2 = {"event_id": "e2", "kind": "EXPANSÃO", "title": "Loja 2", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True}
        opps = gerar_oportunidades_acionaveis([ev1, ev2], self.fontes)
        cons = consolidar_oportunidades_tematicas(opps)
        self.assertEqual(cons[0].governance.scope_type, SCOPE_POSSIBLE_SOLUTION)
        self.assertTrue(cons[0].governance.requires_separate_agreement)

    def test_22_consolidacao_nao_transforma_analitica_em_solucao(self):
        """22. Consolidação de duas recomendações analíticas não cria uma solução de software/projeto."""
        ev1 = {"event_id": "e1", "kind": "REGULAÇÃO", "title": "Norma 1", "entity": "Órgão", "confidence": 0.85, "importance": 80, "evidence_ids": [1]}
        ev2 = {"event_id": "e2", "kind": "REGULAÇÃO", "title": "Norma 2", "entity": "Órgão", "confidence": 0.85, "importance": 80, "evidence_ids": [1]}
        opps = gerar_oportunidades_acionaveis([ev1, ev2], self.fontes)
        cons = consolidar_oportunidades_tematicas(opps)
        self.assertEqual(cons[0].governance.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(cons[0].governance.solution_type)

    def test_23_need_gate_opera_perfeitamente_com_priorizacao(self):
        """23. Need Gate continua rejeitando soluções com evidência insuficiente enquanto calcula prioridade."""
        ev = {"event_id": "e1", "kind": "DIGITAL", "title": "Site atualizado", "entity": "Alpha", "confidence": 0.60, "importance": 50, "evidence_ids": [1], "independent_source_count": 1}
        opp = gerar_oportunidades_acionaveis([ev], self.fontes)[0]
        self.assertEqual(opp.governance.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(opp.governance.solution_type)
        self.assertGreater(opp.intelligence_priority, 0.0)

    def test_24_requires_separate_agreement_permanece_intacto(self):
        """24. requires_separate_agreement permanece True em todas as oportunidades não-contratadas."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}
        opp = gerar_oportunidades_acionaveis([ev], self.fontes)[0]
        self.assertTrue(opp.governance.requires_separate_agreement)

    def test_25_renderizacao_html_e_pdf_com_prioridade(self):
        """25. HTML e PDF renderizam os pacotes executivos com badges de prioridade de inteligência."""
        eventos = [{"event_id": "e1", "kind": "EXPANSÃO", "title": "Nova Loja Centro", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True}]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        self.assertIn("oportunidades", pacote)
        self.assertIn("intelligence_priority", pacote["oportunidades"][0])

        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("Prioridade:", html)

        pdf_path = gerar_pdf(pacote, self.fontes, eventos, self.ambiente, {}, pasta_execucao=self.temp_path, run_id="pdf_prio_test")
        self.assertIsNotNone(pdf_path)
        self.assertTrue(Path(pdf_path).exists())


if __name__ == "__main__":
    unittest.main()
