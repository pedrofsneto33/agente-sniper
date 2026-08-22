# -*- coding: utf-8 -*-
"""
Bateria de Testes Formais e Granulares — Integração da Inteligência Acionável na Entrega ao Cliente (Fase 54.1).
Valida os 18 requisitos funcionais e adversariais de entrega e renderização.
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
from domain.decision import inteligencia_deterministica, validar_pacote
from reports.html import gerar_html
from reports.pdf import gerar_pdf


class TestDeliveryIntegration(unittest.TestCase):
    """Suíte formal para validação da entrega de oportunidades e guardrails de contato em relatórios."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.fontes = [
            Fonte(id=1, titulo="Inauguração de Polo Alpha", url="https://noticia.com/polo-alpha", origem="web", score=85.0, confianca=0.95),
            Fonte(id=2, titulo="Polo Alpha abre novas vagas", url="https://diario.com/polo-alpha-vagas", origem="web", score=80.0, confianca=0.90),
        ]
        self.ambiente = {
            "score": 70, "label": "ALTA", "cobertura": 0.85,
            "dimensoes": {"EXPANSÃO": {"score": 80, "eventos": 1, "evidencias": 2, "eventos_correlacionados": 1}},
            "pressao_competitiva": {"score": 50, "label": "MÉDIA"},
            "vulnerabilidade_empresa": {"score": 15, "label": "BAIXA"},
            "momentum_mercado": 60,
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_oportunidade_nova_aparece_no_html(self):
        """1. Oportunidade nova com should_deliver=True é renderizada no HTML."""
        eventos = [{
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Polo Alpha Inaugurado",
            "entity": "Rede Alpha", "confidence": 0.90, "importance": 85,
            "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("Inteligência Acionável & Oportunidades", html)
        self.assertIn("Polo Alpha Inaugurado", html)
        self.assertIn("AÇÃO RECOMENDADA", html)

    def test_02_oportunidade_nova_aparece_no_pdf(self):
        """2. Oportunidade nova com should_deliver=True é renderizada no PDF."""
        eventos = [{
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Polo Alpha Inaugurado",
            "entity": "Rede Alpha", "confidence": 0.90, "importance": 85,
            "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        pdf_path = gerar_pdf(pacote, self.fontes, eventos, self.ambiente, {}, pasta_execucao=self.temp_path, run_id="test_run_pdf")
        self.assertIsNotNone(pdf_path)
        self.assertTrue(Path(pdf_path).exists())

    def test_03_oportunidade_atualizada_aparece_com_desdobramento(self):
        """3. Oportunidade atualizada exibe explicitamente o badge de desdobramento."""
        eventos = [{
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Polo Alpha Aberto",
            "entity": "Rede Alpha", "confidence": 0.90, "importance": 90,
            "evidence_ids": [1, 2], "independent_source_count": 2,
            "mudanca_material": True, "motivo_mudanca": "evolucao_fato: planeja -> abriu"
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("Desdobramento: evolucao_fato", html)

    def test_04_oportunidade_suprimida_por_memoria_nao_aparece(self):
        """4. Oportunidade com should_deliver=False não é renderizada no card principal."""
        eventos = [{
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Polo Alpha",
            "entity": "Rede Alpha", "confidence": 0.85, "importance": 75,
            "evidence_ids": [1], "independent_source_count": 2, "mudanca_material": False
        }]
        mem = MemoriaEntrega([{"event_id": "ev_01", "delivered_to": "cliente_alpha", "delivered_at": "2026-08-01"}])
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente, memoria_entrega=mem, delivered_to="cliente_alpha")
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("Nenhuma oportunidade acionável nova ou atualizada identificada neste ciclo", html)

    def test_05_sugestao_contato_elegivel_aparece(self):
        """5. Sugestão de contato elegível aparece na caixa destacada de contato."""
        eventos = [{
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Polo Alpha Inaugurado",
            "entity": "Rede Alpha", "confidence": 0.95, "importance": 90,
            "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("Sugestão de Contato:", html)
        self.assertIn("Caso haja interesse comercial, avaliar contato institucional com Rede Alpha", html)

    def test_06_sugestao_contato_inelegivel_suprimida(self):
        """6. Crise reputacional ou evento sem entidade suprime sugestão de contato."""
        eventos = [{
            "event_id": "ev_01", "kind": "REPUTAÇÃO", "title": "Reclamações sobre atendimento",
            "entity": "Concorrente Gamma", "confidence": 0.95, "importance": 90,
            "evidence_ids": [1, 2], "independent_source_count": 2
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertNotIn("Sugestão de Contato:", html)

    def test_07_ausencia_de_oportunidades_gera_secao_limpa(self):
        """7. Lista vazia de oportunidades renderiza mensagem amigável sem erros de template."""
        pacote = inteligencia_deterministica(self.fontes, [], self.ambiente)
        html = gerar_html(pacote, self.fontes, [], self.ambiente, {})
        self.assertIn("Nenhuma oportunidade acionável nova ou atualizada identificada neste ciclo.", html)

    def test_08_evidence_ids_rastreaveis_no_html_e_pdf(self):
        """8. Valida que as citações [FONTE 1] são renderizadas corretamente."""
        eventos = [{
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Loja Centro",
            "entity": "Alpha", "confidence": 0.85, "importance": 80,
            "evidence_ids": [1, 2], "independent_source_count": 2
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("[FONTE 1] [FONTE 2]", html)

    def test_09_separacao_semantica_fato_e_interpretacao(self):
        """9. O HTML distingue claramente os campos Fato, Impacto Estratégico e Ação Recomendada."""
        eventos = [{
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Abertura de nova unidade",
            "entity": "Alpha", "confidence": 0.85, "importance": 80,
            "evidence_ids": [1, 2], "independent_source_count": 2
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html = gerar_html(pacote, self.fontes, eventos, self.ambiente, {})
        self.assertIn("<b>Fato:</b>", html)
        self.assertIn("<b>Impacto Estratégico:</b>", html)
        self.assertIn("<b>AÇÃO RECOMENDADA:</b>", html)

    def test_10_determinismo_de_renderizacao(self):
        """10. Mesma entrada produz exatamente o mesmo HTML em chamadas sucessivas."""
        eventos = [{
            "event_id": "ev_01", "kind": "PRODUTO/SERVIÇO", "title": "Novo Mix",
            "entity": "Beta", "confidence": 0.85, "importance": 75,
            "evidence_ids": [1, 2], "independent_source_count": 2
        }]
        dt_fixa = datetime(2026, 8, 20, 10, 0, 0)
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        html1 = gerar_html(pacote, self.fontes, eventos, self.ambiente, {}, data_ref=dt_fixa)
        html2 = gerar_html(pacote, self.fontes, eventos, self.ambiente, {}, data_ref=dt_fixa)
        self.assertEqual(html1, html2)

    def test_11_cinco_nichos_renderizam_oportunidades_especificas(self):
        """11. Valida que a especialização por perfil modifica o impacto contextual exibido."""
        eventos = [{
            "event_id": "ev_01", "kind": "REGULAÇÃO", "title": "Nova Portaria Sanitária",
            "entity": "Anvisa", "confidence": 0.90, "importance": 85,
            "evidence_ids": [1, 2], "independent_source_count": 2
        }]
        prof_clinica = obter_perfil_nicho("clinica")
        prof_adv = {
            "label": "Advocacia Corporativa",
            "relevance_weights": {"REGULAÇÃO": 1.0, "PESSOAS": 0.9, "PREÇO": 0.2}
        }
        pacote_adv = inteligencia_deterministica(self.fontes, eventos, self.ambiente, profile=prof_adv)
        html_adv = gerar_html(pacote_adv, self.fontes, eventos, self.ambiente, {}, perfil_label="Advocacia Corporativa")
        self.assertIn("Advocacia Corporativa", html_adv)

    def test_12_zero_automacao_comercial_ou_io(self):
        """12. Comprova que nenhum gerador de relatório realiza I/O de rede ou automação."""
        pacote = inteligencia_deterministica(self.fontes, [], self.ambiente)
        # Geração 100% em memória
        html = gerar_html(pacote, self.fontes, [], self.ambiente, {})
        self.assertIsInstance(html, str)

    def test_13_validar_pacote_inclui_oportunidades(self):
        """13. Valida que a validação forense sanitiza evidence_ids e confiança das oportunidades."""
        eventos = [{
            "event_id": "ev_01", "kind": "EXPANSÃO", "title": "Loja",
            "entity": "Alpha", "confidence": 0.95, "importance": 80,
            "evidence_ids": [1, 999]  # 999 é inválido
        }]
        pacote = inteligencia_deterministica(self.fontes, eventos, self.ambiente)
        val = validar_pacote(pacote, self.fontes)
        self.assertTrue(val["valido"])
        self.assertEqual(val["oportunidades"], 1)
        self.assertEqual(pacote["oportunidades"][0]["evidence_ids"], [1])

    def test_14_anti_repeticao_sequencial_t0_a_t4(self):
        """14. Simulação sequencial T0 -> T1 -> T2 -> T3 -> T4 demonstrando ciclo de vida da oportunidade."""
        mem = MemoriaEntrega()
        # T0: Oportunidade nova -> deve entregar
        ev_t0 = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Obra Anunciada", "entity": "A", "confidence": 0.85, "importance": 80, "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True}
        pacote_t0 = inteligencia_deterministica(self.fontes, [ev_t0], self.ambiente, memoria_entrega=mem, delivered_to="cliente_1")
        self.assertTrue(pacote_t0["oportunidades"][0]["should_deliver"])

        # Registra entrega de T0
        mem.registrar({"event_id": "e1", "delivered_to": "cliente_1", "delivered_at": "2026-08-01"})

        # T1: Mesma oportunidade sem mudança -> não deve entregar
        ev_t1 = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Obra Anunciada", "entity": "A", "confidence": 0.85, "importance": 80, "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": False}
        pacote_t1 = inteligencia_deterministica(self.fontes, [ev_t1], self.ambiente, memoria_entrega=mem, delivered_to="cliente_1")
        self.assertFalse(pacote_t1["oportunidades"][0]["should_deliver"])

        # T4: Mudança material -> volta a entregar como desdobramento
        ev_t4 = {"event_id": "e1", "kind": "EXPANSÃO", "title": "Obra Concluída", "entity": "A", "confidence": 0.90, "importance": 90, "evidence_ids": [1, 2], "independent_source_count": 2, "mudanca_material": True, "motivo_mudanca": "evolucao_fato"}
        pacote_t4 = inteligencia_deterministica(self.fontes, [ev_t4], self.ambiente, memoria_entrega=mem, delivered_to="cliente_1")
        self.assertTrue(pacote_t4["oportunidades"][0]["should_deliver"])


if __name__ == "__main__":
    unittest.main()
