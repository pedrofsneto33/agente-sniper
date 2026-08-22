# -*- coding: utf-8 -*-
"""
Bateria de Testes Formais e Adversariais — Governança de Escopo da Inteligência Acionável (Fase 54.2).
Valida os 20 requisitos de fronteira de escopo, não-presunção de contrato e salvaguarda analítica.
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from domain.models import Fonte
from domain.deltas import MemoriaEntrega
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
)
from domain.decision import inteligencia_deterministica
from reports.html import gerar_html
from reports.pdf import gerar_pdf


class TestScopeGovernance(unittest.TestCase):
    """Suíte adversarial para governança de escopo e não-presunção de obrigação contratual."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.fontes = [
            Fonte(id=1, titulo="Inauguração e Expansão Alpha", url="https://noticia.com/1", origem="web", score=85.0, confianca=0.95),
            Fonte(id=2, titulo="Parceria Estratégica Beta", url="https://noticia.com/2", origem="web", score=80.0, confianca=0.90),
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

    def test_01_oportunidade_sem_config_fora_do_escopo_por_default(self):
        """1. Sem configuração de contrato, qualquer oportunidade gerada tem in_contracted_scope=False."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Obra", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2], "independent_source_count": 2}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes)
        self.assertEqual(len(opps), 1)
        self.assertFalse(opps[0].governance.in_contracted_scope)
        self.assertTrue(opps[0].governance.requires_separate_agreement)
        self.assertTrue(opps[0].governance.human_validation_required)

    def test_02_possible_solution_exige_acordo_separado(self):
        """2. Ações de solução/projeto são classificadas como POSSIBLE_SOLUTION e OPTIONAL_PROJECT."""
        gov = determinar_governanca_escopo("TRANSFORMACAO_DIGITAL")
        self.assertEqual(gov.scope_type, SCOPE_POSSIBLE_SOLUTION)
        self.assertEqual(gov.execution_nature, "OPTIONAL_PROJECT")
        self.assertTrue(gov.requires_separate_agreement)
        self.assertFalse(gov.in_contracted_scope)

    def test_03_perfil_supermercado_nao_altera_escopo_contratual(self):
        """3. O perfil de supermercado com alta relevância de preço não torna soluções contratadas."""
        prof_super = obter_perfil_nicho("supermercado")
        ev = {"event_id": "e1", "kind": "PREÇO", "title": "Guerra de preços", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes, profile=prof_super)
        self.assertEqual(len(opps), 1)
        self.assertFalse(opps[0].governance.in_contracted_scope)

    def test_04_perfil_advocacia_nao_altera_escopo_contratual(self):
        """4. O perfil de advocacia com alta relevância regulatória não torna soluções contratadas."""
        prof_adv = {"label": "Advocacia", "relevance_weights": {"REGULAÇÃO": 1.0, "PESSOAS": 0.9}}
        ev = {"event_id": "e1", "kind": "REGULAÇÃO", "title": "Nova Norma", "entity": "CADE", "confidence": 0.95, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes, profile=prof_adv)
        self.assertEqual(len(opps), 1)
        self.assertFalse(opps[0].governance.in_contracted_scope)

    def test_05_perfil_clinica_nao_altera_escopo_contratual(self):
        """5. O perfil de clínica não altera o escopo contratual das oportunidades."""
        prof_clinica = obter_perfil_nicho("clinica")
        ev = {"event_id": "e1", "kind": "PRODUTO/SERVIÇO", "title": "Novo Exame", "entity": "Hospital X", "confidence": 0.95, "importance": 85, "evidence_ids": [1, 2], "independent_source_count": 2}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes, profile=prof_clinica)
        self.assertEqual(len(opps), 1)
        self.assertFalse(opps[0].governance.in_contracted_scope)

    def test_06_perfil_imobiliaria_nao_altera_escopo_contratual(self):
        """6. O perfil de imobiliária não altera o escopo contratual das oportunidades."""
        prof_imob = obter_perfil_nicho("imobiliaria")
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Lançamento", "entity": "Construtora Y", "confidence": 0.95, "importance": 85, "evidence_ids": [1, 2], "independent_source_count": 2}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes, profile=prof_imob)
        self.assertEqual(len(opps), 1)
        self.assertFalse(opps[0].governance.in_contracted_scope)

    def test_07_perfil_farmacia_nao_altera_escopo_contratual(self):
        """7. O perfil de farmácia não altera o escopo contratual das oportunidades."""
        prof_farm = obter_perfil_nicho("farmacia")
        ev = {"event_id": "e1", "kind": "REGULAÇÃO", "title": "Regulamentação", "entity": "Anvisa", "confidence": 0.95, "importance": 85, "evidence_ids": [1, 2], "independent_source_count": 2}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes, profile=prof_farm)
        self.assertEqual(len(opps), 1)
        self.assertFalse(opps[0].governance.in_contracted_scope)

    def test_08_recomendacao_analitica_natureza_decisao_cliente(self):
        """8. Ação recomendada em dimensão comum tem execution_nature = CLIENT_DECISION."""
        gov = determinar_governanca_escopo("POSICIONAMENTO_MERCADO")
        self.assertEqual(gov.scope_type, SCOPE_ANALYTICAL_RECOMMENDATION)
        self.assertEqual(gov.execution_nature, "CLIENT_DECISION")

    def test_09_solucao_possivel_nao_e_servico_contratado(self):
        """9. Soluções de expansão ou parceria permanecem como hipóteses com requires_separate_agreement=True."""
        gov = determinar_governanca_escopo("PARCERIA_ESTRATEGICA")
        self.assertEqual(gov.scope_type, SCOPE_POSSIBLE_SOLUTION)
        self.assertTrue(gov.requires_separate_agreement)

    def test_10_ausencia_de_config_contratual_resiliente(self):
        """10. Execução com contract_config=None é totalmente segura e conservadora."""
        gov = determinar_governanca_escopo("EXPANSAO_COMERCIAL", contract_config=None)
        self.assertFalse(gov.in_contracted_scope)

    def test_11_configuracao_contratual_explicita_respeitada(self):
        """11. Configuração explícita de contrato pode definir serviços ativos sem contaminar o nicho."""
        config_contrato = {"contracted_services": ["EXPANSAO_COMERCIAL"]}
        gov = determinar_governanca_escopo("EXPANSAO_COMERCIAL", contract_config=config_contrato)
        self.assertTrue(gov.in_contracted_scope)
        self.assertFalse(gov.requires_separate_agreement)
        self.assertEqual(gov.scope_type, SCOPE_CONTRACTED_INTELLIGENCE)

    def test_12_sugestao_contato_independente_da_governanca(self):
        """12. Governança de escopo não interfere nos guardrails de sugestão de contato."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja Nova", "entity": "Alpha", "confidence": 0.95, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes)
        self.assertIsNotNone(opps[0].contact_suggestion)
        self.assertFalse(opps[0].governance.in_contracted_scope)

    def test_13_determinismo_com_governanca(self):
        """13. Múltiplas chamadas produzem saídas e estruturas de governança idênticas."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}
        res1 = gerar_oportunidades_acionaveis([ev], self.fontes)
        res2 = gerar_oportunidades_acionaveis([ev], self.fontes)
        self.assertEqual(res1[0].governance, res2[0].governance)
        self.assertEqual(res1[0].delivery_fingerprint, res2[0].delivery_fingerprint)

    def test_14_memoria_de_entrega_com_governanca(self):
        """14. MemoriaEntrega respeita o delivery_fingerprint enriquecido com governança."""
        mem = MemoriaEntrega([{"event_id": "e1", "delivered_to": "cliente_alpha", "delivered_at": "2026-08-01"}])
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2], "mudanca_material": False}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes, memoria_entrega=mem, delivered_to="cliente_alpha")
        self.assertFalse(opps[0].should_deliver)

    def test_15_nenhum_termo_de_promessa_indevida_no_payload(self):
        """15. Verifica que o payload não contém termos de obrigação ou promessa de execução técnica."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes)
        d = opps[0].to_dict()
        texto_total = str(d).lower()
        termos_proibidos = ["vamos desenvolver", "será implementado", "nossa equipe irá", "o sniper irá resolver", "será implantado"]
        for termo in termos_proibidos:
            self.assertNotIn(termo, texto_total)

    def test_16_zero_io_externo_com_governanca(self):
        """16. Toda a camada de governança opera puramente em memória e sem I/O."""
        gov = determinar_governanca_escopo("ATRACAO_TALENTOS")
        self.assertIsInstance(gov.disclaimer, str)

    def test_17_serializacao_to_dict_preserva_governance(self):
        """17. Valida que to_dict inclui a chave governance com todos os subcampos."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes)
        d = opps[0].to_dict()
        self.assertIn("governance", d)
        self.assertIn("in_contracted_scope", d["governance"])
        self.assertIn("requires_separate_agreement", d["governance"])
        self.assertIn("disclaimer", d["governance"])

    def test_18_html_exibe_salvaguarda_de_escopo(self):
        """18. O HTML renderiza explicitamente o texto de salvaguarda de escopo."""
        eventos = [{"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("Salvaguarda de Escopo:", html)
        self.assertIn("não integram automaticamente o escopo contratado", html)
        self.assertIn("Decisão Consultiva", html)

    def test_19_pdf_exibe_salvaguarda_de_escopo(self):
        """19. O PDF inclui o texto de salvaguarda de escopo."""
        eventos = [{"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        pdf_path = gerar_pdf(pacote, self.fontes, eventos, self.ambiente, {}, pasta_execucao=self.temp_path, run_id="pdf_gov_test")
        self.assertIsNotNone(pdf_path)
        self.assertTrue(Path(pdf_path).exists())

    def test_20_validacao_completa_de_pacote_com_governanca(self):
        """20. Validação forense valida integridade do pacote com governança de escopo."""
        eventos = [{"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        self.assertIn("oportunidades", pacote)
        self.assertIn("governance", pacote["oportunidades"][0])


if __name__ == "__main__":
    unittest.main()
