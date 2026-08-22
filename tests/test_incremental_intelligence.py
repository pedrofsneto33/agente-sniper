# -*- coding: utf-8 -*-
"""
Bateria de Testes Formais e Adversariais — Inteligência Incremental e Memória de Entrega (Fase 53.2).
Valida os 20 requisitos adversariais da Fase 53.2.
"""
import os
import unittest
from datetime import datetime

from domain.deltas import (
    analisar_inteligencia_incremental,
    calcular_delta_eventos,
    verificar_mudanca_material,
    calcular_relevancia_nicho,
    RegistroEntrega,
    MemoriaEntrega,
    ESTADO_EVENTO_NOVO,
    ESTADO_EVENTO_RECORRENTE,
    ESTADO_EVENTO_ATUALIZADO,
    ESTADO_EVENTO_CONTINUIDADE,
    ESTADO_EVENTO_SEM_MUDANCA,
    ESTADO_EVENTO_INATIVO_EXPIRADO,
)
from domain.profiles import obter_perfil_nicho
from domain.identity import sha1, url_normalizada


class TestIncrementalIntelligence(unittest.TestCase):
    """Suíte abrangente e adversarial para inteligência incremental e memória de entrega."""

    def setUp(self):
        self.hoje = datetime(2026, 8, 20)

    def test_01_mesmo_evento_mesmas_fontes_sem_novidade(self):
        """1. Mesmo evento com mesmas fontes é classificado como SEM_MUDANCA ou CONTINUIDADE."""
        ev = {"event_id": "ev1", "event_key": "k1", "kind": "MARKETING", "title": "Campanha Institucional", "entity": "Alvo", "date": "2026-08-10", "importance": 40, "source_urls": ["https://noticia.com/1"]}
        res = analisar_inteligencia_incremental([ev], [ev], hoje=self.hoje)
        self.assertEqual(len(res["novos"]), 0)
        self.assertEqual(len(res["atualizados"]), 0)
        self.assertEqual(len(res["sem_mudanca"]), 1)

    def test_02_mesmo_evento_urls_equivalentes_sem_falsa_novidade(self):
        """2. URLs equivalentes com parâmetros de tracking (utm_source) não disparam falsa novidade."""
        ev_hist = {"event_id": "ev1", "event_key": "k1", "kind": "EXPANSÃO", "title": "Nova filial", "entity": "Alvo", "date": "2026-08-10", "importance": 50, "source_urls": ["https://portal.com/noticia-1"]}
        ev_atual = {"event_id": "ev1", "event_key": "k1", "kind": "EXPANSÃO", "title": "Nova filial", "entity": "Alvo", "date": "2026-08-10", "importance": 50, "source_urls": ["https://portal.com/noticia-1?utm_source=twitter&utm_medium=social#header"]}
        is_mat, motivo = verificar_mudanca_material(ev_atual, ev_hist)
        self.assertFalse(is_mat)
        self.assertEqual(motivo, "sem_mudanca_material")

    def test_03_mesmo_evento_nova_fonte_independente(self):
        """3. Adição de nova fonte independente dispara nova_corroboracao."""
        ev_hist = {"event_id": "ev1", "event_key": "k1", "kind": "REPUTAÇÃO", "title": "Reclamações", "entity": "Alvo", "source_urls": ["https://g1.com/1"], "date": "2026-08-10"}
        ev_atual = {"event_id": "ev1", "event_key": "k1", "kind": "REPUTAÇÃO", "title": "Reclamações", "entity": "Alvo", "source_urls": ["https://g1.com/1", "https://uol.com.br/2"], "date": "2026-08-15"}
        is_mat, motivo = verificar_mudanca_material(ev_atual, ev_hist)
        self.assertTrue(is_mat)
        self.assertIn("nova_corroboracao", motivo)

    def test_04_mesma_quantidade_mas_fontes_diferentes(self):
        """4. Mesma quantidade (2 fontes) mas com URLs e domínios diferentes é detectado como nova evidência."""
        ev_hist = {"event_id": "ev1", "event_key": "k1", "kind": "REGULAÇÃO", "title": "Processo", "entity": "Alvo", "source_urls": ["https://fonteA.com/1", "https://fonteB.com/2"], "date": "2026-08-10"}
        ev_atual = {"event_id": "ev1", "event_key": "k1", "kind": "REGULAÇÃO", "title": "Processo", "entity": "Alvo", "source_urls": ["https://fonteC.com/3", "https://fonteD.com/4"], "date": "2026-08-15"}
        is_mat, motivo = verificar_mudanca_material(ev_atual, ev_hist)
        self.assertTrue(is_mat)
        self.assertIn("nova_corroboracao", motivo)

    def test_05_mudanca_cosmetica_sem_atualizacao(self):
        """5. Mudança puramente cosmética de pontuação ou caixa alta/baixa não gera atualização."""
        ev_hist = {"event_id": "ev1", "event_key": "k1", "kind": "PREÇO", "title": "Ofertas Especiais", "entity": "Alvo", "importance": 50, "date": "2026-08-10"}
        ev_atual = {"event_id": "ev1", "event_key": "k1", "kind": "PREÇO", "title": "ofertas especiais!!!", "entity": "Alvo", "importance": 50, "date": "2026-08-15"}
        is_mat, motivo = verificar_mudanca_material(ev_atual, ev_hist)
        self.assertFalse(is_mat)

    def test_06_mudanca_factual_atualizado(self):
        """6. Mudança factual no título (anuncia -> inaugurou) resulta em ATUALIZADO."""
        ev_hist = {"event_id": "ev1", "event_key": "k1", "kind": "EXPANSÃO", "title": "Empresa planeja nova unidade", "entity": "Alvo", "date": "2026-08-01"}
        ev_atual = {"event_id": "ev1", "event_key": "k1", "kind": "EXPANSÃO", "title": "Empresa abriu nova unidade", "entity": "Alvo", "date": "2026-08-15"}
        res = analisar_inteligencia_incremental([ev_atual], [ev_hist], hoje=self.hoje)
        self.assertEqual(len(res["atualizados"]), 1)
        self.assertEqual(res["atualizados"][0]["estado_incremental"], ESTADO_EVENTO_ATUALIZADO)
        self.assertTrue(res["atualizados"][0]["deve_reapresentar"])

    def test_07_evento_antigo_alta_relevancia_continuidade(self):
        """7. Evento antigo com alta relevância sem alteração permanece em CONTINUIDADE."""
        ev = {"event_id": "ev1", "event_key": "k1", "kind": "REGULAÇÃO", "title": "Inquérito Administrativo", "entity": "Alvo", "importance": 85, "confidence": 0.95, "date": "2026-08-10"}
        res = analisar_inteligencia_incremental([ev], [ev], hoje=self.hoje)
        self.assertEqual(len(res["continuidade"]), 1)
        self.assertEqual(res["continuidade"][0]["estado_incremental"], ESTADO_EVENTO_CONTINUIDADE)

    def test_08_continuidade_condensacao_apos_10_ciclos(self):
        """8. Evento que persiste por 10 ciclos consecutivos sem alteração material é condensado."""
        ev_corrente = {"event_id": "ev1", "event_key": "k1", "kind": "REGULAÇÃO", "title": "Inquérito", "entity": "Alvo", "importance": 85, "confidence": 0.95, "date": "2026-08-10"}
        ev_hist = dict(ev_corrente)
        ev_hist["continuity_cycles"] = 9  # já esteve em continuidade por 9 ciclos

        res = analisar_inteligencia_incremental([ev_corrente], [ev_hist], hoje=self.hoje)
        self.assertEqual(len(res["continuidade"]), 1)
        ev_res = res["continuidade"][0]
        self.assertEqual(ev_res["continuity_cycles"], 10)
        self.assertTrue(ev_res["condensado"])
        self.assertFalse(ev_res["deve_reapresentar"])

    def test_09_cadencia_semanal(self):
        """9. Execução sob cadência semanal (7 dias)."""
        ev = {"event_id": "ev1", "event_key": "k1", "kind": "DIGITAL", "title": "Novo aplicativo", "date": "2026-08-15"}
        res = analisar_inteligencia_incremental([ev], [], cadencia_dias=7, hoje=self.hoje)
        self.assertEqual(res["total_ativos"], 1)

    def test_10_cadencia_quinzenal(self):
        """10. Execução sob cadência quinzenal (15 dias)."""
        ev = {"event_id": "ev1", "event_key": "k1", "kind": "DIGITAL", "title": "Novo aplicativo", "date": "2026-08-08"}
        res = analisar_inteligencia_incremental([ev], [], cadencia_dias=15, hoje=self.hoje)
        self.assertEqual(res["total_ativos"], 1)

    def test_11_cadencia_mensal(self):
        """11. Execução sob cadência mensal (30 dias)."""
        ev = {"event_id": "ev1", "event_key": "k1", "kind": "DIGITAL", "title": "Novo aplicativo", "date": "2026-07-25"}
        res = analisar_inteligencia_incremental([ev], [], cadencia_dias=30, hoje=self.hoje)
        self.assertEqual(res["total_ativos"], 1)

    def test_12_primeiro_relatorio_sem_historico(self):
        """12. Primeiro relatório sem histórico classifica 100% dos eventos como NOVO."""
        evs = [
            {"event_id": "e1", "event_key": "k1", "kind": "PREÇO", "title": "Oferta", "importance": 70},
            {"event_id": "e2", "event_key": "k2", "kind": "EXPANSÃO", "title": "Loja", "importance": 80},
        ]
        res = analisar_inteligencia_incremental(evs, [], hoje=self.hoje)
        self.assertEqual(len(res["novos"]), 2)
        self.assertEqual(res["taxa_novidade"], 1.0)
        self.assertTrue(res["tem_mudanca_material"])

    def test_13_evento_ja_entregue_sem_mudanca_nao_reapresentar(self):
        """13. Evento já entregue ao cliente sem mudança material tem deve_reapresentar False se não for novidade."""
        ev = {"event_id": "ev1", "event_key": "k1", "kind": "MARKETING", "title": "Campanha", "importance": 40, "date": "2026-08-10"}
        mem_entrega = MemoriaEntrega([
            {"event_id": "ev1", "event_key": "k1", "delivered_to": "cliente_alpha", "delivered_at": "2026-08-10T10:00:00"}
        ])
        res = analisar_inteligencia_incremental([ev], [ev], memoria_entrega=mem_entrega, delivered_to="cliente_alpha", hoje=self.hoje)
        self.assertEqual(len(res["sem_mudanca"]), 1)
        self.assertTrue(res["sem_mudanca"][0]["entregue_anteriormente"])
        self.assertFalse(res["sem_mudanca"][0]["deve_reapresentar"])

    def test_14_evento_ja_entregue_com_mudanca_material_reapresentar(self):
        """14. Evento já entregue que sofreu alteração material é reapresentado como ATUALIZADO."""
        ev_hist = {"event_id": "ev1", "event_key": "k1", "kind": "EXPANSÃO", "title": "Anúncio de obra", "importance": 50, "date": "2026-08-01"}
        ev_atual = {"event_id": "ev1", "event_key": "k1", "kind": "EXPANSÃO", "title": "Obra concluída e aberta", "importance": 85, "date": "2026-08-15"}
        mem_entrega = MemoriaEntrega([
            {"event_id": "ev1", "event_key": "k1", "delivered_to": "cliente_alpha", "delivered_at": "2026-08-01T10:00:00"}
        ])
        res = analisar_inteligencia_incremental([ev_atual], [ev_hist], memoria_entrega=mem_entrega, delivered_to="cliente_alpha", hoje=self.hoje)
        self.assertEqual(len(res["atualizados"]), 1)
        self.assertTrue(res["atualizados"][0]["deve_reapresentar"])
        self.assertEqual(res["atualizados"][0]["estado_incremental"], ESTADO_EVENTO_ATUALIZADO)

    def test_15_evento_ja_entregue_com_nova_evidencia_relevante(self):
        """15. Evento já entregue que recebeu nova fonte independente gera atualização material."""
        ev_hist = {"event_id": "ev1", "event_key": "k1", "kind": "REGULAÇÃO", "title": "Fiscalização", "source_urls": ["https://fonte1.com/1"], "date": "2026-08-01"}
        ev_atual = {"event_id": "ev1", "event_key": "k1", "kind": "REGULAÇÃO", "title": "Fiscalização", "source_urls": ["https://fonte1.com/1", "https://fonte2.com/2"], "date": "2026-08-15"}
        mem_entrega = MemoriaEntrega([
            {"event_id": "ev1", "event_key": "k1", "delivered_to": "cliente_beta", "delivered_at": "2026-08-01T10:00:00"}
        ])
        res = analisar_inteligencia_incremental([ev_atual], [ev_hist], memoria_entrega=mem_entrega, delivered_to="cliente_beta", hoje=self.hoje)
        self.assertEqual(len(res["atualizados"]), 1)
        self.assertIn("nova_corroboracao", res["atualizados"][0]["motivo_mudanca"])

    def test_16_evento_coletado_mas_nao_entregue_tratado_como_novo(self):
        """16. Evento presente no banco geral mas nunca entregue ao cliente é NOVO para aquele cliente."""
        ev = {"event_id": "ev1", "event_key": "k1", "kind": "PESSOAS", "title": "Nova contratação", "importance": 70, "date": "2026-08-15"}
        mem_entrega = MemoriaEntrega()  # vazia para o cliente_novo
        res = analisar_inteligencia_incremental([ev], [], memoria_entrega=mem_entrega, delivered_to="cliente_novo", hoje=self.hoje)
        self.assertEqual(len(res["novos"]), 1)
        self.assertFalse(res["novos"][0]["entregue_anteriormente"])
        self.assertTrue(res["novos"][0]["deve_reapresentar"])

    def test_17_isolamento_de_memoria_entre_clientes(self):
        """17. A entrega para o Cliente A não suprime a novidade para o Cliente B."""
        ev = {"event_id": "ev1", "event_key": "k1", "kind": "PRODUTO/SERVIÇO", "title": "Novo produto", "importance": 70, "date": "2026-08-15"}
        mem_entrega = MemoriaEntrega([
            {"event_id": "ev1", "event_key": "k1", "delivered_to": "cliente_alpha", "delivered_at": "2026-08-15T10:00:00"}
        ])
        # Consulta para Cliente Alpha (já entregue)
        self.assertTrue(mem_entrega.foi_entregue("k1", delivered_to="cliente_alpha"))
        # Consulta para Cliente Beta (nunca entregue)
        self.assertFalse(mem_entrega.foi_entregue("k1", delivered_to="cliente_beta"))

    def test_18_relevancia_multi_nicho_sem_contaminacao(self):
        """18. Valida separação estrita de pesos entre nichos (Advocacia vs Supermercado)."""
        fato_preco = {"kind": "PREÇO", "importance": 80, "confidence": 0.9}
        fato_reg = {"kind": "REGULAÇÃO", "importance": 80, "confidence": 0.9}

        prof_super = obter_perfil_nicho("supermercado")
        prof_adv = {
            "label": "Advocacia",
            "relevance_weights": {
                "REGULAÇÃO": 1.00, "PESSOAS": 0.95, "REPUTAÇÃO": 0.90,
                "EXPANSÃO": 0.85, "PRODUTO/SERVIÇO": 0.80, "PARCERIA": 0.75, "PREÇO": 0.20
            }
        }
        rel_super_prc = calcular_relevancia_nicho(fato_preco, prof_super)
        rel_adv_prc = calcular_relevancia_nicho(fato_preco, prof_adv)
        rel_adv_reg = calcular_relevancia_nicho(fato_reg, prof_adv)

        self.assertGreater(rel_super_prc, rel_adv_prc * 3)
        self.assertGreater(rel_adv_reg, rel_adv_prc * 4)

    def test_19_determinismo_absoluto(self):
        """19. Execuções repetidas com mesmos inputs geram saídas 100% idênticas."""
        evs = [
            {"event_id": "e1", "event_key": "k1", "kind": "PESSOAS", "title": "Contratação", "importance": 60},
            {"event_id": "e2", "event_key": "k2", "kind": "REGULAÇÃO", "title": "Autuação", "importance": 90},
        ]
        res1 = analisar_inteligencia_incremental(evs, [], hoje=self.hoje)
        res2 = analisar_inteligencia_incremental(evs, [], hoje=self.hoje)
        self.assertEqual(res1, res2)

    def test_20_compatibilidade_contrato_calcular_delta_eventos(self):
        """20. Valida retrocompatibilidade completa com a assinatura canônica de calcular_delta_eventos."""
        ev = {"event_id": "e1", "event_key": "k1", "kind": "EXPANSÃO", "title": "Inauguração", "importance": 75}
        res = calcular_delta_eventos([ev], [], hoje=self.hoje)
        self.assertIn("novos", res)
        self.assertIn("recorrentes", res)
        self.assertIn("expirados", res)
        self.assertIn("total_ativos", res)
        self.assertIn("taxa_renovacao", res)
        self.assertIn("atualizados", res)
        self.assertIn("continuidade", res)
        self.assertIn("sem_mudanca", res)


if __name__ == "__main__":
    unittest.main()
