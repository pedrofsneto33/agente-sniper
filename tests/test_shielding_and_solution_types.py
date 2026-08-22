# -*- coding: utf-8 -*-
"""
Bateria de Testes Formais e Granulares — Blindagem Semântica dos Sinais e Subtipos de Solução (Fase 54.4).
Valida os requisitos de blindagem textual, categorização de soluções e evolução da memória de oportunidades.
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from domain.models import Fonte
from domain.deltas import MemoriaEntrega, RegistroEntrega
from domain.profiles import obter_perfil_nicho
from domain.opportunities import (
    ActionableOpportunity,
    ScopeGovernance,
    determinar_governanca_escopo,
    gerar_oportunidades_acionaveis,
    SCOPE_CONTRACTED_INTELLIGENCE,
    SCOPE_ANALYTICAL_RECOMMENDATION,
    SCOPE_POSSIBLE_SOLUTION,
    SCOPE_OPTIONAL_EXPANSION_SERVICE,
    SOLUTION_SOFTWARE_CUSTOMIZADO,
    SOLUTION_PROCESSO_INTERNO,
    SOLUTION_CONSULTORIA_ADICIONAL,
    SOLUTION_INFRAESTRUTURA_INTEGRACAO,
    SOLUTION_OUTRO,
)
from domain.decision import inteligencia_deterministica
from reports.html import gerar_html
from reports.pdf import gerar_pdf


class TestShieldingAndSolutionTypes(unittest.TestCase):
    """Suíte para validação da blindagem semântica de sinais e subtipologias de soluções."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.fontes = [
            Fonte(id=1, titulo="Inovação Digital Alpha", url="https://noticia.com/1", origem="web", score=85.0, confianca=0.95),
            Fonte(id=2, titulo="Expansão Regional Beta", url="https://noticia.com/2", origem="web", score=80.0, confianca=0.90),
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

    def test_01_blindagem_semantica_urgencia_e_acao_sinais_html(self):
        """1. HTML apresenta 'Urgência de Monitoramento' e 'AÇÃO SUGERIDA PARA AVALIAÇÃO'."""
        eventos = [{"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja Centro", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("Urgência de Monitoramento:", html)
        self.assertIn("AÇÃO SUGERIDA PARA AVALIAÇÃO:", html)
        self.assertIn("Salvaguarda de Sinais:", html)
        self.assertIn("não representam ordens operacionais nem obrigação de execução técnica", html)

    def test_02_blindagem_semantica_sinais_pdf(self):
        """2. PDF apresenta salvaguarda e ação sugerida para avaliação nos sinais."""
        eventos = [{"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja Centro", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        pdf_path = gerar_pdf(pacote, self.fontes, eventos, self.ambiente, {}, pasta_execucao=self.temp_path, run_id="pdf_shielding_test")
        self.assertIsNotNone(pdf_path)
        self.assertTrue(Path(pdf_path).exists())

    def test_03_subtipo_software_customizado(self):
        """3. Ação TRANSFORMACAO_DIGITAL gera solution_type = SOFTWARE_CUSTOMIZADO."""
        gov = determinar_governanca_escopo("TRANSFORMACAO_DIGITAL")
        self.assertEqual(gov.scope_type, SCOPE_POSSIBLE_SOLUTION)
        self.assertEqual(gov.solution_type, SOLUTION_SOFTWARE_CUSTOMIZADO)
        self.assertFalse(gov.in_contracted_scope)
        self.assertTrue(gov.requires_separate_agreement)

    def test_04_subtipo_infraestrutura_integracao(self):
        """4. Ação EXPANSAO_COMERCIAL gera solution_type = INFRAESTRUTURA_OU_INTEGRACAO."""
        gov = determinar_governanca_escopo("EXPANSAO_COMERCIAL")
        self.assertEqual(gov.scope_type, SCOPE_POSSIBLE_SOLUTION)
        self.assertEqual(gov.solution_type, SOLUTION_INFRAESTRUTURA_INTEGRACAO)
        self.assertTrue(gov.requires_separate_agreement)

    def test_05_subtipo_consultoria_adicional(self):
        """5. Ação PARCERIA_ESTRATEGICA gera solution_type = CONSULTORIA_ADICIONAL."""
        gov = determinar_governanca_escopo("PARCERIA_ESTRATEGICA")
        self.assertEqual(gov.scope_type, SCOPE_POSSIBLE_SOLUTION)
        self.assertEqual(gov.solution_type, SOLUTION_CONSULTORIA_ADICIONAL)
        self.assertTrue(gov.requires_separate_agreement)

    def test_06_subtipo_processo_interno(self):
        """6. Ação COMPLIANCE_REGULATORIO gera recomendação analítica para decisão do cliente."""
        gov = determinar_governanca_escopo("COMPLIANCE_REGULATORIO")
        self.assertEqual(gov.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(gov.solution_type)
        self.assertEqual(gov.execution_nature, "CLIENT_DECISION")

    def test_07_subtipo_outro_default(self):
        """7. Ação genérica desconhecida gera recomendação analítica pura sem solução."""
        gov = determinar_governanca_escopo("ACAO_GENERICA_DESCONHECIDA")
        self.assertEqual(gov.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertIsNone(gov.solution_type)

    def test_08_serializacao_to_dict_com_solution_type(self):
        """8. to_dict de ActionableOpportunity serializa solution_type e identified_need corretamente."""
        ev = {"event_id": "e1", "kind": "DIGITAL", "title": "Novo App", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True}
        prof = {"label": "Empresa Tech", "relevance_weights": {"DIGITAL": 0.90}}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes, profile=prof)
        d = opps[0].to_dict()
        self.assertEqual(d["governance"]["solution_type"], SOLUTION_SOFTWARE_CUSTOMIZADO)
        self.assertIsNotNone(d["identified_need"])
        self.assertIsNotNone(d["need_rationale"])

    def test_09_multi_nicho_independente_para_solution_type(self):
        """9. Subtipo de solução se comporta de forma idêntica em diferentes perfis de nicho."""
        ev = {"event_id": "e1", "kind": "DIGITAL", "title": "Portal Online", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True}
        prof_super = obter_perfil_nicho("supermercado")
        prof_adv = {"label": "Advocacia", "relevance_weights": {"DIGITAL": 0.90}}
        opp_super = gerar_oportunidades_acionaveis([ev], self.fontes, profile=prof_super)[0]
        opp_adv = gerar_oportunidades_acionaveis([ev], self.fontes, profile=prof_adv)[0]
        self.assertEqual(opp_super.governance.solution_type, opp_adv.governance.solution_type)
        self.assertEqual(opp_super.governance.solution_type, SOLUTION_SOFTWARE_CUSTOMIZADO)

    def test_10_memoria_entrega_com_fingerprint_suprime_identica(self):
        """10. Oportunidade idêntica com mesmo fingerprint é suprimida pela MemoriaEntrega."""
        ev = {"event_id": "e1", "kind": "DIGITAL", "title": "Novo App", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2], "mudanca_material": False}
        opp_t0 = gerar_oportunidades_acionaveis([ev], self.fontes)[0]
        
        mem = MemoriaEntrega()
        mem.registrar(RegistroEntrega(
            event_id="e1", event_key="e1", delivered_at="2026-08-01",
            delivered_to="cliente_alpha", fingerprint_entrega=opp_t0.delivery_fingerprint
        ))

        opp_t1 = gerar_oportunidades_acionaveis([ev], self.fontes, memoria_entrega=mem, delivered_to="cliente_alpha")[0]
        self.assertFalse(opp_t1.should_deliver)

    def test_11_memoria_entrega_com_fingerprint_permite_reentrega_em_evolucao(self):
        """11. Evolução da hipótese (fingerprint diferente) permite reentrega na MemoriaEntrega."""
        mem = MemoriaEntrega()
        # Registra entrega anterior com fingerprint antigo e marcação de evolução
        mem.registrar(RegistroEntrega(
            event_id="e1", event_key="e1", delivered_at="2026-08-01",
            delivered_to="cliente_alpha", fingerprint_entrega="fingerprint_antigo_de_outra_versao",
            metadata={"evolucao_hipotese": True}
        ))

        ev_atual = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Nova Unidade", "entity": "Alpha", "confidence": 0.9, "importance": 85, "evidence_ids": [1, 2], "mudanca_material": False}
        opp_atual = gerar_oportunidades_acionaveis([ev_atual], self.fontes, memoria_entrega=mem, delivered_to="cliente_alpha")[0]
        # Como o fingerprint da oportunidade atual difere do registrado anteriormente, é entregue
        self.assertTrue(opp_atual.should_deliver)

    def test_12_foi_entregue_com_fingerprint_metodo_direto(self):
        """12. Valida o método puro foi_entregue_com_fingerprint em MemoriaEntrega."""
        mem = MemoriaEntrega()
        mem.registrar(RegistroEntrega(
            event_id="ev_42", event_key="ev_42", delivered_at="2026-08-01",
            delivered_to="cliente_x", fingerprint_entrega="fp_exato_123"
        ))
        self.assertTrue(mem.foi_entregue_com_fingerprint("ev_42", "fp_exato_123", delivered_to="cliente_x"))
        self.assertFalse(mem.foi_entregue_com_fingerprint("ev_42", "fp_diferente", delivered_to="cliente_x"))
        self.assertFalse(mem.foi_entregue_com_fingerprint("ev_inexistente", "fp_exato_123", delivered_to="cliente_x"))


if __name__ == "__main__":
    unittest.main()
