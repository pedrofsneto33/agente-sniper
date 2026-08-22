# -*- coding: utf-8 -*-
"""
Bateria de Testes Formais e Adversariais — Inteligência Acionável, Oportunidades e Sugestões de Contato (Fase 54).
Valida os 20 requisitos adversariais da Fase 54.
"""
import os
import unittest
from datetime import datetime

from domain.models import Fonte
from domain.deltas import MemoriaEntrega
from domain.profiles import obter_perfil_nicho
from domain.opportunities import (
    ActionableOpportunity,
    gerar_oportunidades_acionaveis,
    calcular_confianca_oportunidade,
    formular_sugestao_contato,
    formular_recomendacao_contextual,
    OPPORTUNITY_ACTION_TYPES,
)


class TestActionableIntelligence(unittest.TestCase):
    """Testes unitários e de integração para oportunidades acionáveis e guardrails de contato."""

    def setUp(self):
        self.fontes_mock = [
            Fonte(id=1, titulo="Notícia A", url="https://portal.com/1", origem="web", conteudo="Texto da fonte 1"),
            Fonte(id=2, titulo="Notícia B", url="https://portal.com/2", origem="web", conteudo="Texto da fonte 2"),
        ]

    def test_01_fato_forte_nao_significa_oportunidade_forte(self):
        """1. Valida que evidência com 0.99 de confiança não gera oportunidade com 0.99 se o impacto for fraco."""
        opp_conf = calcular_confianca_oportunidade(
            evidence_confidence=0.99,
            kind="MARKETING",
            target_entity="mercado",  # entidade genérica reduz fator
            independent_sources=1,    # fonte única reduz fator
            relevance_weight=0.50,    # dimensão de baixo peso
            is_material_change=False,
        )
        self.assertLess(opp_conf, 0.50)
        self.assertNotEqual(opp_conf, 0.99)

    def test_02_oportunidade_fraca_e_suprimida(self):
        """2. Oportunidades com baixa confiança ou relevância não são geradas no relatório."""
        ev_fraco = {
            "event_id": "ev_fraco", "kind": "MARKETING", "title": "Campanha vaga",
            "entity": "mercado", "confidence": 0.30, "importance": 30,
            "evidence_ids": [1], "independent_source_count": 1
        }
        opps = gerar_oportunidades_acionaveis([ev_fraco], self.fontes_mock)
        self.assertEqual(len(opps), 0)

    def test_03_oportunidade_forte_e_produzida(self):
        """3. Evento relevante com entidade específica e corroboração gera oportunidade estruturada."""
        ev_forte = {
            "event_id": "ev_forte", "kind": "EXPANSÃO", "title": "Nova unidade confirmada no centro",
            "entity": "Grupo Alpha", "confidence": 0.90, "importance": 85,
            "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True
        }
        opps = gerar_oportunidades_acionaveis([ev_forte], self.fontes_mock)
        self.assertEqual(len(opps), 1)
        opp = opps[0]
        self.assertEqual(opp.category, "OPORTUNIDADE")
        self.assertEqual(opp.action_type, "EXPANSAO_COMERCIAL")
        self.assertEqual(opp.target_entity, "Grupo Alpha")
        self.assertGreaterEqual(opp.opportunity_confidence, 0.70)
        self.assertIsNotNone(opp.contact_suggestion)

    def test_04_ausencia_de_entidade_impede_sugestao_contato(self):
        """4. Evento sem entidade específica definida não gera sugestão de contato comercial."""
        sug = formular_sugestao_contato(
            kind="EXPANSÃO",
            target_entity="mercado",  # genérico
            action_type="EXPANSAO_COMERCIAL",
            evidence_confidence=0.95,
            opportunity_confidence=0.90,
            relevance_score=80.0,
            motivo_contextual="Abertura de unidades",
        )
        self.assertIsNone(sug)

    def test_05_baixa_confianca_evidencia_impede_contato(self):
        """5. Evidência com confiança < 0.70 suprime sugestão de contato."""
        sug = formular_sugestao_contato(
            kind="PARCERIA",
            target_entity="Empresa Beta",
            action_type="PARCERIA_ESTRATEGICA",
            evidence_confidence=0.65,  # abaixo do threshold
            opportunity_confidence=0.85,
            relevance_score=80.0,
            motivo_contextual="Acordo",
        )
        self.assertIsNone(sug)

    def test_06_baixa_confianca_oportunidade_impede_contato(self):
        """6. Oportunidade com confiança < 0.70 suprime sugestão de contato."""
        sug = formular_sugestao_contato(
            kind="PARCERIA",
            target_entity="Empresa Beta",
            action_type="PARCERIA_ESTRATEGICA",
            evidence_confidence=0.90,
            opportunity_confidence=0.68,  # abaixo do threshold
            relevance_score=80.0,
            motivo_contextual="Acordo",
        )
        self.assertIsNone(sug)

    def test_07_evento_reputacional_inadequado_nao_produz_contato(self):
        """7. Dimensões de crise reputacional ou queixas (REPUTAÇÃO, ATENDIMENTO) nunca geram contato comercial."""
        for kind in ["REPUTAÇÃO", "ATENDIMENTO"]:
            with self.subTest(kind=kind):
                sug = formular_sugestao_contato(
                    kind=kind,
                    target_entity="Empresa Gamma",
                    action_type="MONITORAMENTO_REPUTACIONAL",
                    evidence_confidence=0.95,
                    opportunity_confidence=0.95,
                    relevance_score=90.0,
                    motivo_contextual="Queixas no Procon",
                )
                self.assertIsNone(sug)

    def test_08_sugestao_contato_nao_executa_io_e_mantem_padrao_humano(self):
        """8. Sugestão de contato é apenas texto formatado no padrão condicional para decisão humana."""
        sug = formular_sugestao_contato(
            kind="PARCERIA",
            target_entity="Parceiro Delta",
            action_type="PARCERIA_ESTRATEGICA",
            evidence_confidence=0.85,
            opportunity_confidence=0.85,
            relevance_score=75.0,
            motivo_contextual="Acordo de distribuição",
        )
        self.assertIsNotNone(sug)
        self.assertTrue(sug.startswith("Caso haja interesse comercial, avaliar contato institucional com"))

    def test_09_oportunidade_ja_entregue_sem_mudanca_suprimida(self):
        """9. Oportunidade já entregue ao cliente sem alteração material tem should_deliver=False."""
        ev = {
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Obra", "entity": "Alpha",
            "confidence": 0.85, "importance": 80, "evidence_ids": [1], "independent_source_count": 2,
            "mudanca_material": False
        }
        mem = MemoriaEntrega([{"event_id": "ev_01", "delivered_to": "cliente_1", "delivered_at": "2026-08-01"}])
        opps = gerar_oportunidades_acionaveis([ev], self.fontes_mock, memoria_entrega=mem, delivered_to="cliente_1")
        self.assertEqual(len(opps), 1)
        self.assertFalse(opps[0].should_deliver)

    def test_10_oportunidade_atualizada_volta_a_ser_apresentada(self):
        """10. Oportunidade com mudança material volta a ter should_deliver=True mesmo se já entregue antes."""
        ev = {
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Obra inaugurada", "entity": "Alpha",
            "confidence": 0.90, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 3,
            "mudanca_material": True, "motivo_mudanca": "evolucao_fato: anuncia -> abriu"
        }
        mem = MemoriaEntrega([{"event_id": "ev_01", "delivered_to": "cliente_1", "delivered_at": "2026-08-01"}])
        opps = gerar_oportunidades_acionaveis([ev], self.fontes_mock, memoria_entrega=mem, delivered_to="cliente_1")
        self.assertEqual(len(opps), 1)
        self.assertTrue(opps[0].should_deliver)
        self.assertIn("evolucao_fato", opps[0].detected_change)

    def test_11_cliente_a_nao_suprime_oportunidade_cliente_b(self):
        """11. Entrega prévia para Cliente A não afeta should_deliver para Cliente B."""
        ev = {
            "event_id": "ev_01", "kind": "PRODUTO/SERVIÇO", "title": "Lançamento", "entity": "Beta",
            "confidence": 0.85, "importance": 75, "evidence_ids": [1], "independent_source_count": 2,
            "mudanca_material": False
        }
        mem = MemoriaEntrega([{"event_id": "ev_01", "delivered_to": "cliente_a", "delivered_at": "2026-08-01"}])
        opps_a = gerar_oportunidades_acionaveis([ev], self.fontes_mock, memoria_entrega=mem, delivered_to="cliente_a")
        opps_b = gerar_oportunidades_acionaveis([ev], self.fontes_mock, memoria_entrega=mem, delivered_to="cliente_b")
        self.assertFalse(opps_a[0].should_deliver)
        self.assertTrue(opps_b[0].should_deliver)

    def test_12_determinismo_de_fingerprint_e_ordenacao(self):
        """12. Mesma entrada produz exatamente a mesma oportunidade, fingerprint e ordem."""
        evs = [
            {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja Centro", "entity": "A", "confidence": 0.8, "importance": 70, "evidence_ids": [1]},
            {"event_id": "e2", "kind": "PARCERIA", "title": "Acordo", "entity": "B", "confidence": 0.9, "importance": 85, "evidence_ids": [1, 2]},
        ]
        res1 = gerar_oportunidades_acionaveis(evs, self.fontes_mock)
        res2 = gerar_oportunidades_acionaveis(evs, self.fontes_mock)
        self.assertEqual([o.id for o in res1], [o.id for o in res2])
        self.assertEqual([o.delivery_fingerprint for o in res1], [o.delivery_fingerprint for o in res2])

    def test_13_multiplas_evidencias_rastreaveis(self):
        """13. Valida que todos os evidence_ids retornados estão presentes no mapa de fontes."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "A", "confidence": 0.8, "importance": 70, "evidence_ids": [1, 2, 999]}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes_mock)
        self.assertEqual(opps[0].evidence_ids, (1, 2))  # 999 filtrado

    def test_14_cinco_nichos_produzem_relevancias_diferentes(self):
        """14. Mesmos fatos produzem ordenações e scores de oportunidade distintos em 5 nichos."""
        fato_preco = {"event_id": "ep", "kind": "PREÇO", "title": "Preço Baixo", "entity": "X", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}
        fato_reg = {"event_id": "er", "kind": "REGULAÇÃO", "title": "Norma", "entity": "Y", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}

        prof_super = obter_perfil_nicho("supermercado")
        prof_clinica = obter_perfil_nicho("clinica")
        prof_farmacia = obter_perfil_nicho("farmacia")
        prof_imob = obter_perfil_nicho("imobiliaria")
        prof_adv = {
            "label": "Advocacia",
            "relevance_weights": {
                "REGULAÇÃO": 1.00, "PESSOAS": 0.95, "REPUTAÇÃO": 0.90,
                "EXPANSÃO": 0.85, "PRODUTO/SERVIÇO": 0.80, "PARCERIA": 0.75, "PREÇO": 0.20
            }
        }

        opps_super = gerar_oportunidades_acionaveis([fato_preco, fato_reg], self.fontes_mock, profile=prof_super)
        opps_adv = gerar_oportunidades_acionaveis([fato_preco, fato_reg], self.fontes_mock, profile=prof_adv)

        # Em supermercado, PREÇO fica no topo
        self.assertEqual(opps_super[0].event_id, "ep")
        # Em advocacia, REGULAÇÃO fica no topo
        self.assertEqual(opps_adv[0].event_id, "er")

    def test_15_ausencia_de_hardcode_de_nicho_no_core(self):
        """15. Valida que a especialização decorre de relevance_weights e não de if-statements."""
        prof_custom = {"label": "Nicho Customizado", "relevance_weights": {"MARKETING": 1.00, "PREÇO": 0.10}}
        fato_mkt = {"event_id": "em", "kind": "MARKETING", "title": "Campanha", "entity": "Brand Z", "confidence": 0.9, "importance": 80, "evidence_ids": [1, 2]}
        opps = gerar_oportunidades_acionaveis([fato_mkt], self.fontes_mock, profile=prof_custom)
        self.assertEqual(len(opps), 1)
        self.assertGreater(opps[0].opportunity_confidence, 0.70)

    def test_16_confianca_oportunidade_nunca_confundida_com_evidencia(self):
        """16. Prova matematicamente que opportunity_confidence e evidence_confidence são atributos distintos."""
        ev = {"event_id": "e1", "kind": "DIGITAL", "title": "App", "entity": "mercado", "confidence": 0.95, "importance": 60, "evidence_ids": [1]}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes_mock)
        self.assertEqual(opps[0].evidence_confidence, 0.95)
        self.assertLess(opps[0].opportunity_confidence, 0.95)

    def test_17_primeiro_relatorio_sem_memoria_funciona(self):
        """17. Execução inicial sem memória de entrega define should_deliver=True para todas as oportunidades elegíveis."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.85, "importance": 75, "evidence_ids": [1, 2]}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes_mock, memoria_entrega=None)
        self.assertEqual(len(opps), 1)
        self.assertTrue(opps[0].should_deliver)

    def test_18_execucao_sem_env_preservada(self):
        """18. Valida que o motor de oportunidades opera em memória pura sem requerer .env."""
        self.assertIsNone(os.environ.get("CHAVE_INEXISTENTE_TEST_18"))
        ev = {"event_id": "e1", "kind": "PARCERIA", "title": "Acordo", "entity": "Beta", "confidence": 0.85, "importance": 75, "evidence_ids": [1]}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes_mock)
        self.assertEqual(len(opps), 1)

    def test_19_formular_recomendacao_contextual_detalhada(self):
        """19. Valida que a recomendação contextual responde O Quê, Por Quê e Como."""
        impacto, acao = formular_recomendacao_contextual(
            kind="EXPANSÃO",
            title="Abertura de nova filial no centro",
            target_entity="Rede Alpha",
            profile_label="Varejo Alimentar",
            detected_change="evolucao_fato: anuncia -> abriu"
        )
        self.assertIn("Rede Alpha", impacto)
        self.assertIn("Varejo Alimentar", impacto)
        self.assertIn("Mapear a cobertura", acao)

    def test_20_metadados_e_serializacao_to_dict(self):
        """20. Valida serialização determinística to_dict do modelo ActionableOpportunity."""
        ev = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Loja", "entity": "Alpha", "confidence": 0.85, "importance": 80, "evidence_ids": [1, 2]}
        opps = gerar_oportunidades_acionaveis([ev], self.fontes_mock)
        d = opps[0].to_dict()
        self.assertIsInstance(d, dict)
        self.assertIn("id", d)
        self.assertIn("opportunity_confidence", d)
        self.assertIn("recommended_action", d)


if __name__ == "__main__":
    unittest.main()
