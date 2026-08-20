# -*- coding: utf-8 -*-
"""
Suíte de Testes Formais para Deltas Temporais de Eventos (Fase 33 / Etapa 1).
Cobre os cenários de inteligência temporal e unicidade de pareamento:
1. Evento inédito -> NOVO
2. Mesmo event_key -> RECORRENTE
3. URL diferente, chaves diferentes, mesmo fato -> RECORRENTE (resolução semântica)
4. Fonte diferente, semanas distintas -> RECORRENTE
5. Eventos semanticamente parecidos de entidades distintas -> não colidir (ambos NOVO)
6. Ausência pontual <= 45 dias -> não expirar
7. Histórico > 45 dias sem nova evidência -> INATIVO_EXPIRADO
8. Evento histórico expirado reativado com chave e data novas (idade > 45d vs hoje, delta <= 45d) -> RECORRENTE
9. Determinismo estrito (igualdade do payload completo)
10. Ausência de efeitos colaterais (imutabilidade das entradas)
11. Unicidade de pareamento 1-to-1 (um histórico não é consumido por múltiplos atuais)
12. Prioridade de correspondência exata sobre semântica
13. Pareamento 1-to-1 com múltiplos históricos (distribuição 2-to-2)
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.deltas import (
    calcular_delta_eventos,
    ESTADO_EVENTO_NOVO,
    ESTADO_EVENTO_RECORRENTE,
    ESTADO_EVENTO_INATIVO_EXPIRADO,
)


class TestEventDeltas(unittest.TestCase):
    """Testes unitários formais para a classificação temporal de deltas de eventos."""

    def setUp(self):
        self.hoje_fixo = datetime(2026, 8, 20)

    def test_01_evento_inedito_novo(self):
        """1. Evento atual sem correspondência no histórico é classificado como NOVO."""
        ev1 = {"event_id": "ev_01", "event_key": "k_01", "kind": "EXPANSÃO", "title": "Inauguração Mix Mateus Timon", "entity": "Mateus", "date": "2026-08-15"}
        res = calcular_delta_eventos([ev1], [], hoje=self.hoje_fixo)
        self.assertEqual(len(res["novos"]), 1)
        self.assertEqual(res["novos"][0]["estado_temporal"], ESTADO_EVENTO_NOVO)
        self.assertEqual(res["total_ativos"], 1)
        self.assertEqual(res["taxa_renovacao"], 1.0)

    def test_02_mesmo_event_key_recorrente(self):
        """2. Evento atual com mesmo event_key no histórico é classificado como RECORRENTE."""
        ev1 = {"event_id": "ev_01", "event_key": "k_01", "kind": "EXPANSÃO", "title": "Inauguração Mix Mateus Timon", "entity": "Mateus", "date": "2026-08-15"}
        res = calcular_delta_eventos([ev1], [ev1], hoje=self.hoje_fixo)
        self.assertEqual(len(res["recorrentes"]), 1)
        self.assertEqual(res["recorrentes"][0]["estado_temporal"], ESTADO_EVENTO_RECORRENTE)
        self.assertEqual(res["taxa_renovacao"], 0.0)

    def test_03_url_diferente_mesmo_fato_recorrente(self):
        """3. Matéria em URL e com chave diferente para o mesmo fato resolve via similaridade semântica como RECORRENTE."""
        ev_hist = {"event_id": "ev_01", "event_key": "k_hist_g1", "kind": "EXPANSÃO", "title": "Inauguração Mix Mateus Timon nesta sexta", "entity": "Mateus", "date": "2026-08-15", "source_urls": ["https://g1.com/noticia-1"]}
        ev_atual = {"event_id": "ev_02", "event_key": "k_atual_cv", "kind": "EXPANSÃO", "title": "Inauguração Mix Mateus Timon nesta sexta-feira", "entity": "Mateus", "date": "2026-08-15", "source_urls": ["https://cidadeverde.com/noticia-2"]}
        res = calcular_delta_eventos([ev_atual], [ev_hist], hoje=self.hoje_fixo)
        self.assertEqual(len(res["recorrentes"]), 1)
        self.assertEqual(res["recorrentes"][0]["estado_temporal"], ESTADO_EVENTO_RECORRENTE)
        self.assertEqual(res["recorrentes"][0]["evento_origem_id"], "ev_01")
        self.assertEqual(len(res["novos"]), 0)

    def test_04_fonte_diferente_mesmo_fato_semantico_recorrente(self):
        """4. Fonte diferente em semana posterior cobrindo o mesmo fato resolve via similaridade semântica como RECORRENTE."""
        ev_sem1 = {"event_id": "ev_01", "event_key": "k_sem1", "kind": "EXPANSÃO", "title": "Grupo Mateus anuncia expansão em Timon", "entity": "Mateus", "date": "2026-08-01"}
        ev_sem3 = {"event_id": "ev_02", "event_key": "k_sem3", "kind": "EXPANSÃO", "title": "Grupo Mateus acelera expansão em Timon", "entity": "Mateus", "date": "2026-08-15"}
        res = calcular_delta_eventos([ev_sem3], [ev_sem1], hoje=self.hoje_fixo)
        self.assertEqual(len(res["recorrentes"]), 1)
        self.assertEqual(res["recorrentes"][0]["estado_temporal"], ESTADO_EVENTO_RECORRENTE)
        self.assertEqual(res["recorrentes"][0]["evento_origem_id"], "ev_01")

    def test_05_entidades_distintas_nao_colidem(self):
        """5. Eventos semanticamente idênticos mas de entidades distintas não colidem (ambos NOVO)."""
        ev_mateus = {"event_id": "ev_m", "event_key": "km", "kind": "EXPANSÃO", "title": "Inauguração de nova filial", "entity": "Mateus", "date": "2026-08-15"}
        ev_carvalho = {"event_id": "ev_c", "event_key": "kc", "kind": "EXPANSÃO", "title": "Inauguração de nova filial", "entity": "Carvalho", "date": "2026-08-15"}
        res = calcular_delta_eventos([ev_carvalho], [ev_mateus], hoje=self.hoje_fixo)
        self.assertEqual(len(res["novos"]), 1)
        self.assertEqual(res["novos"][0]["entity"], "Carvalho")

    def test_06_ausencia_dentro_45d_nao_expira(self):
        """6. Evento não observado em T1 mas com data recente (<= 45d) permanece ativo no histórico."""
        ev_recente = {"event_id": "ev_rec", "event_key": "k_rec", "kind": "PREÇO", "title": "Ofertas da Semana", "entity": "Mateus", "date": "2026-08-10"}
        res = calcular_delta_eventos([], [ev_recente], hoje=self.hoje_fixo)
        self.assertEqual(len(res["expirados"]), 0)

    def test_07_evento_mais_de_45d_inativo_expirado(self):
        """7. Evento histórico com > 45 dias sem nova evidência é classificado como INATIVO_EXPIRADO."""
        ev_antigo = {"event_id": "ev_old", "event_key": "k_old", "kind": "MARKETING", "title": "Campanha de Páscoa Antiga", "entity": "Mateus", "date": "2026-06-01"}
        res = calcular_delta_eventos([], [ev_antigo], hoje=self.hoje_fixo)
        self.assertEqual(len(res["expirados"]), 1)
        self.assertEqual(res["expirados"][0]["estado_temporal"], ESTADO_EVENTO_INATIVO_EXPIRADO)
        self.assertGreater(res["expirados"][0]["idade_dias"], 45)

    def test_08_evento_expirado_reativado_recorrente(self):
        """8. Evento histórico com > 45d de idade em relação a hoje é reativado por nova evidência com chave e data distintas."""
        # Histórico tem 56 dias de idade em relação a hoje=2026-08-20 (expiraria se não houvesse nova evidência)
        ev_antigo = {"event_id": "ev_old", "event_key": "k_old_junho", "kind": "MARKETING", "title": "Grande Festival de Prêmios Mateus", "entity": "Mateus", "date": "2026-06-25"}
        # Nova evidência 38 dias após o evento antigo (<= 45d cluster_days) com chave diferente
        ev_reativado = {"event_id": "ev_reat", "event_key": "k_reat_agosto", "kind": "MARKETING", "title": "Grande Festival de Prêmios Mateus Edição Especial", "entity": "Mateus", "date": "2026-08-02"}
        res = calcular_delta_eventos([ev_reativado], [ev_antigo], hoje=self.hoje_fixo)
        self.assertEqual(len(res["recorrentes"]), 1)
        self.assertEqual(res["recorrentes"][0]["estado_temporal"], ESTADO_EVENTO_RECORRENTE)
        self.assertEqual(res["recorrentes"][0]["evento_origem_id"], "ev_old")
        self.assertEqual(len(res["expirados"]), 0, "O evento antigo não deve aparecer em expirados pois foi reativado")

    def test_09_determinismo_estrito(self):
        """9. A função calcular_delta_eventos é estritamente determinística no payload completo em 10 execuções."""
        ev_sem1 = {"event_id": "ev_01", "event_key": "k_sem1", "kind": "EXPANSÃO", "title": "Grupo Mateus anuncia expansão em Timon", "entity": "Mateus", "date": "2026-08-01"}
        ev_sem3 = {"event_id": "ev_02", "event_key": "k_sem3", "kind": "EXPANSÃO", "title": "Grupo Mateus acelera expansão em Timon", "entity": "Mateus", "date": "2026-08-15"}
        ev_antigo = {"event_id": "ev_old", "event_key": "k_old", "kind": "MARKETING", "title": "Campanha de Páscoa Antiga", "entity": "Mateus", "date": "2026-06-01"}
        runs = [calcular_delta_eventos([ev_sem3], [ev_sem1, ev_antigo], hoje=self.hoje_fixo) for _ in range(10)]
        for r in runs:
            self.assertEqual(r, runs[0])

    def test_10_ausencia_efeitos_colaterais(self):
        """10. A execução não muta os dicionários originais de entrada."""
        ev = {"event_id": "ev_01", "event_key": "k_01", "kind": "EXPANSÃO", "title": "Expansão", "entity": "Mateus", "date": "2026-08-15"}
        copia = dict(ev)
        calcular_delta_eventos([ev], [ev], hoje=self.hoje_fixo)
        self.assertEqual(ev, copia)

    def test_11_unicidade_pareamento_1_to_1(self):
        """11. Um evento histórico H1 não pode ser consumido por múltiplos eventos atuais (A1 consome H1 -> RECORRENTE, A2 -> NOVO)."""
        h1 = {"event_id": "ev_h1", "event_key": "k_h1", "kind": "EXPANSÃO", "title": "Inauguração Mix Mateus Timon", "entity": "Mateus", "date": "2026-08-10"}
        a1 = {"event_id": "ev_a1", "event_key": "k_a1", "kind": "EXPANSÃO", "title": "Inauguração Mix Mateus Timon", "entity": "Mateus", "date": "2026-08-15"}
        a2 = {"event_id": "ev_a2", "event_key": "k_a2", "kind": "EXPANSÃO", "title": "Inauguração Mix Mateus Timon", "entity": "Mateus", "date": "2026-08-15"}
        res = calcular_delta_eventos([a1, a2], [h1], hoje=self.hoje_fixo)
        self.assertEqual(len(res["recorrentes"]), 1, "Apenas 1 evento atual deve consumir H1")
        self.assertEqual(res["recorrentes"][0]["evento_origem_id"], "ev_h1")
        self.assertEqual(len(res["novos"]), 1, "O segundo evento atual sem histórico disponível torna-se NOVO")
        self.assertEqual(res["novos"][0]["event_id"], "ev_a2")
        self.assertEqual(len(res["expirados"]), 0)

    def test_12_prioridade_exata_sobre_semantica(self):
        """12. Correspondência exata por event_key tem prioridade estrita sobre candidatos semânticos parciais."""
        h_exato = {"event_id": "ev_hexato", "event_key": "k_exato", "kind": "EXPANSÃO", "title": "Inauguração Timon", "entity": "Mateus", "date": "2026-08-15"}
        h_semantico = {"event_id": "ev_hsem", "event_key": "k_sem", "kind": "EXPANSÃO", "title": "Inauguração Timon Especial", "entity": "Mateus", "date": "2026-08-15"}
        a1 = {"event_id": "ev_a1", "event_key": "k_exato", "kind": "EXPANSÃO", "title": "Inauguração Timon", "entity": "Mateus", "date": "2026-08-15"}
        res = calcular_delta_eventos([a1], [h_semantico, h_exato], hoje=self.hoje_fixo)
        self.assertEqual(len(res["recorrentes"]), 1)
        self.assertEqual(res["recorrentes"][0]["evento_origem_id"], "ev_hexato", "Deve parear com o match exato de event_key")

    def test_13_pareamento_1_to_1_com_multiplos_historicos(self):
        """13. Dois eventos atuais distintos conseguem parear 1-to-1 com dois históricos distintos (distribuição 2-to-2)."""
        h1 = {"event_id": "ev_h1", "event_key": "k_h1", "kind": "EXPANSÃO", "title": "Inauguração Mix Mateus Timon", "entity": "Mateus", "date": "2026-08-10"}
        h2 = {"event_id": "ev_h2", "event_key": "k_h2", "kind": "PREÇO", "title": "Festival de Ofertas Hortifrúti", "entity": "Mateus", "date": "2026-08-10"}
        a1 = {"event_id": "ev_a1", "event_key": "k_a1", "kind": "EXPANSÃO", "title": "Inauguração Mix Mateus Timon", "entity": "Mateus", "date": "2026-08-15"}
        a2 = {"event_id": "ev_a2", "event_key": "k_a2", "kind": "PREÇO", "title": "Festival de Ofertas Hortifrúti", "entity": "Mateus", "date": "2026-08-15"}
        res = calcular_delta_eventos([a1, a2], [h1, h2], hoje=self.hoje_fixo)
        self.assertEqual(len(res["recorrentes"]), 2)
        origens = {r["evento_origem_id"] for r in res["recorrentes"]}
        self.assertEqual(origens, {"ev_h1", "ev_h2"})
        self.assertEqual(len(res["novos"]), 0)
        self.assertEqual(len(res["expirados"]), 0)


if __name__ == "__main__":
    unittest.main()
