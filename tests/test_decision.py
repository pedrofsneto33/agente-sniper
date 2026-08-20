# -*- coding: utf-8 -*-
"""
Suíte de Testes Formais para Motor de Decisão e Validação Forense de Evidências (Fase 34).
Cobre:
1. Geração determinística do pacote executivo e presença das chaves canônicas.
2. Formatação dos 4 parágrafos do resumo executivo e prioridades 30/60/90.
3. Detecção e listagem de lacunas de informação por score dimensional e data.
4. Fallback de lacunas quando todas as dimensões estão cobertas.
5. validar_ids_sinais() com IDs válidos -> (True, "ok").
6. validar_ids_sinais() com IDs inválidos -> (False, "IDs inválidos: [X, Y]").
7. validar_pacote() deduplicação e ordenação determinística de evidence_ids.
8. validar_pacote() clamping estrito da confiança do sinal ao teto da evidência.
9. validar_pacote() expurgo de sinais sem evidências válidas.
10. validar_pacote() validação de concorrentes contra o corpus textual das fontes.
11. Resiliência a entradas vazias e estruturas incompletas.
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.models import Fonte
from domain.decision import (
    inteligencia_deterministica,
    validar_ids_sinais,
    validar_pacote,
)


class TestDecisionEngine(unittest.TestCase):
    """Testes unitários formais para inteligência determinística e validação forense."""

    def setUp(self):
        self.fontes = [
            Fonte(
                id=1,
                titulo="Mateus inaugura novo atacarejo em Teresina",
                url="https://mateus.com.br/inauguracao",
                origem="web",
                conteudo="O Grupo Mateus abriu hoje sua nova loja em Teresina com foco em atacado e varejo.",
                data_publicacao="2026-08-15",
                score=85.0,
                confianca=0.92,
                atual=True
            ),
            Fonte(
                id=2,
                titulo="Carvalho Super amplia ofertas no setor de alimentos",
                url="https://carvalho.com.br/ofertas",
                origem="web",
                conteudo="O Supermercado Carvalho anunciou promoções agressivas em alimentos.",
                data_publicacao="2026-08-14",
                score=78.0,
                confianca=0.75,
                atual=True
            )
        ]

        self.events = [
            {
                "event_id": "EVT_01",
                "event_key": "EVT_01",
                "kind": "EXPANSÃO",
                "title": "Inauguração Mix Mateus",
                "importance": 85,
                "confidence": 0.90,
                "evidence_ids": [1],
                "independent_source_count": 2,
                "date": "2026-08-15"
            },
            {
                "event_id": "EVT_02",
                "event_key": "EVT_02",
                "kind": "PREÇO",
                "title": "Campanha de Ofertas Carvalho",
                "importance": 70,
                "confidence": 0.80,
                "evidence_ids": [2],
                "independent_source_count": 1,
                "date": "2026-08-14"
            }
        ]

        self.ambiente = {
            "score": 75,
            "label": "ALTA",
            "dimensoes": {
                "EXPANSÃO": {"score": 80, "eventos": [self.events[0]]},
                "PREÇO": {"score": 70, "eventos": [self.events[1]]},
                "REPUTAÇÃO": {"score": 50, "eventos": []}
            },
            "pressao_competitiva": {"score": 60, "label": "ALTA"},
            "vulnerabilidade_empresa": {"score": 20, "label": "BAIXA"}
        }

    def test_01_geracao_pacote_e_chaves_canonicas(self):
        """1. Valida geração determinística do pacote executivo e presença das chaves canônicas."""
        pacote = inteligencia_deterministica(self.fontes, self.events, self.ambiente)

        self.assertIn("resumo_executivo", pacote)
        self.assertIn("sinais", pacote)
        self.assertIn("concorrencia", pacote)
        self.assertIn("prioridades_30", pacote)
        self.assertIn("prioridades_60", pacote)
        self.assertIn("prioridades_90", pacote)
        self.assertIn("lacunas", pacote)

        self.assertEqual(len(pacote["resumo_executivo"]), 4)
        self.assertIsInstance(pacote["sinais"], list)
        self.assertGreater(len(pacote["sinais"]), 0)

    def test_02_resumo_executivo_conteudo(self):
        """2. Valida formatação correta de texto do resumo executivo."""
        pacote = inteligencia_deterministica(self.fontes, self.events, self.ambiente)
        resumo = pacote["resumo_executivo"]

        self.assertIn("2 evidências válidas e 2 eventos canônicos", resumo[0])
        self.assertIn("75/100 (ALTA)", resumo[1])
        self.assertIn("vulnerabilidade externa/operacional estimada está em 20/100", resumo[1])
        self.assertIn("pressão competitiva externa está em 60/100 (ALTA)", resumo[2])
        self.assertIn("EXPANSÃO", resumo[3])

    def test_03_deteccao_de_lacunas(self):
        """3. Valida detecção de lacunas quando scores de dimensões são baixos (<35) ou eventos sem data."""
        ambiente_lacunar = {
            "score": 30,
            "label": "BAIXA",
            "dimensoes": {
                "PREÇO": {"score": 10},
                "REPUTAÇÃO": {"score": 20},
                "EXPANSÃO": {"score": 15}
            }
        }
        events_sem_data = [
            {"event_id": "E1", "kind": "MARKETING", "title": "Campanha", "importance": 50, "evidence_ids": [1]}
        ]

        pacote = inteligencia_deterministica(self.fontes, events_sem_data, ambiente_lacunar)
        lacunas = pacote["lacunas"]

        self.assertEqual(len(lacunas), 4)
        self.assertTrue(any("preço" in l.lower() for l in lacunas))
        self.assertTrue(any("reputação" in l.lower() for l in lacunas))
        self.assertTrue(any("expansão" in l.lower() for l in lacunas))
        self.assertTrue(any("data verificável" in l.lower() for l in lacunas))

    def test_04_fallback_de_lacunas(self):
        """4. Valida mensagem padrão quando não há lacunas críticas."""
        pacote = inteligencia_deterministica(self.fontes, self.events, self.ambiente)
        self.assertEqual(pacote["lacunas"], ["Não foram detectadas lacunas críticas nas dimensões monitoradas."])

    def test_05_validar_ids_sinais_sucesso(self):
        """5. Valida que validar_ids_sinais aceita pacote com IDs de evidência existentes."""
        pacote = {
            "sinais": [{"titulo": "S1", "evidence_ids": [1, 2]}],
            "concorrencia": [{"nome": "Mateus", "evidence_ids": [1]}]
        }
        ok, reason = validar_ids_sinais(pacote, {1, 2, 3})
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_06_validar_ids_sinais_rejeicao(self):
        """6. Valida que validar_ids_sinais rejeita IDs inexistentes com formatação exata."""
        pacote = {
            "sinais": [{"titulo": "S1", "evidence_ids": [1, 99]}],
            "concorrencia": [{"nome": "Mateus", "evidence_ids": [42]}]
        }
        ok, reason = validar_ids_sinais(pacote, {1, 2})
        self.assertFalse(ok)
        self.assertEqual(reason, "IDs inválidos: [42, 99]")

    def test_07_validar_pacote_clamping_confianca_e_deduplicacao(self):
        """7. Valida clamping de confiança da evidência e ordenação/deduplicação de IDs."""
        # Fonte 1 tem confiança 0.92, Fonte 2 tem confiança 0.75
        # Sinal com evidence_ids=[2, 2] e confianca declarada 0.95 -> deve ser clamped para 0.75 e ids=[2]
        pacote = {
            "sinais": [
                {"titulo": "Sinal Preço", "evidence_ids": [2, 2], "confianca": 0.95}
            ],
            "concorrencia": []
        }
        res = validar_pacote(pacote, self.fontes)
        self.assertTrue(res["valido"])
        self.assertEqual(res["sinais"], 1)
        self.assertEqual(res["ids_validos"], 2)

        sinal_saneado = pacote["sinais"][0]
        self.assertEqual(sinal_saneado["evidence_ids"], [2])
        self.assertAlmostEqual(sinal_saneado["confianca"], 0.75, places=2)

    def test_08_validar_pacote_expurgo_sinais_sem_evidencia(self):
        """8. Valida expurgo de sinais que não possuem nenhuma evidência válida."""
        pacote = {
            "sinais": [
                {"titulo": "Sinal Válido", "evidence_ids": [1], "confianca": 0.8},
                {"titulo": "Sinal Órfão", "evidence_ids": [999], "confianca": 0.8},
                {"titulo": "Sinal Sem IDs", "evidence_ids": [], "confianca": 0.8}
            ],
            "concorrencia": []
        }
        res = validar_pacote(pacote, self.fontes)
        self.assertFalse(res["valido"], "Valido deve ser False pois continha IDs inválidos na checagem inicial")
        self.assertEqual(len(pacote["sinais"]), 1)
        self.assertEqual(pacote["sinais"][0]["titulo"], "Sinal Válido")

    def test_09_validar_pacote_concorrente_no_corpus(self):
        """9. Valida que concorrentes cujo nome não consta no corpus das fontes são expurgados."""
        pacote = {
            "sinais": [{"titulo": "S1", "evidence_ids": [1]}],
            "concorrencia": [
                {"nome": "Mateus", "evidence_ids": [1]},           # "Mateus" existe no conteúdo da Fonte 1
                {"nome": "Assaí Atacadista", "evidence_ids": [1]}  # "Assaí" não existe no conteúdo das fontes
            ]
        }
        res = validar_pacote(pacote, self.fontes)
        self.assertEqual(len(pacote["concorrencia"]), 1)
        self.assertEqual(pacote["concorrencia"][0]["nome"], "Mateus")

    def test_10_resiliencia_entradas_vazias(self):
        """10. Valida comportamento gracioso com listas vazias."""
        pacote_vazio = inteligencia_deterministica([], [], {})
        self.assertIsInstance(pacote_vazio, dict)
        self.assertEqual(len(pacote_vazio["sinais"]), 0)

        res_val = validar_pacote({"sinais": [], "concorrencia": []}, [])
        self.assertFalse(res_val["valido"])
        self.assertEqual(res_val["sinais"], 0)


if __name__ == "__main__":
    unittest.main()
