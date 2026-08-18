# -*- coding: utf-8 -*-
"""
Testes Unitários de Detecção e Agrupamento de Eventos — Agente Sniper v11.8.1
Cobre: _primary_event_kind, canonical_event_key, eventos_sao_mesmo_fato, criar_eventos.
"""
import sys
import unittest
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import agente_sniper_v11_8 as sniper


class TestEvents(unittest.TestCase):

    def setUp(self):
        self.empresa = sniper.EMPRESA_ALVO

    def test_01_primary_event_kind_classificacao(self):
        """Testa classificação temática automática baseada em regras léxicas."""
        f_exp = sniper.Fonte(id=1, titulo="Inauguração de nova filial", url="https://u.com/1", origem="web", conteudo="abertura de nova loja no shopping")
        kind_exp, _ = sniper._primary_event_kind(f_exp)
        self.assertEqual(kind_exp, "EXPANSÃO")

        f_preco = sniper.Fonte(id=2, titulo="Supermercado anuncia ofertas e desconto", url="https://u.com/2", origem="web", conteudo="promocao encarte de precos baixos")
        kind_preco, _ = sniper._primary_event_kind(f_preco)
        self.assertEqual(kind_preco, "PREÇO")

        f_pessoas = sniper.Fonte(id=3, titulo="Empresa abre 50 vagas de emprego", url="https://u.com/3", origem="web", conteudo="processo seletivo contratacao de pessoal")
        kind_pessoas, _ = sniper._primary_event_kind(f_pessoas)
        self.assertEqual(kind_pessoas, "PESSOAS")

    def test_02_canonical_event_key_estabilidade(self):
        """Testa determinismo e tamanho do hash canônico de 24 caracteres."""
        f1 = sniper.Fonte(
            id=1, titulo="Carvalho Super inaugura loja 25", url="https://u.com/loja25",
            origem="web", conteudo="Inauguração em Teresina", data_publicacao="2026-08-10",
            alias_empresa=self.empresa, cidade_confirmada=True, estado_confirmado=True,
            escopo="local", entidade=self.empresa
        )
        k1 = sniper.canonical_event_key(f1, "EXPANSÃO")
        k2 = sniper.canonical_event_key(f1, "EXPANSÃO")
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 24)

    def test_03_eventos_sao_mesmo_fato_similaridade_e_data(self):
        """Testa heurística de consolidação temporal e semântica de eventos."""
        # Dois eventos com mesma data e títulos com alta similaridade (>0.70 ou >0.55 tokens) -> mesmo fato
        e1 = {
            "entity": self.empresa, "kind": "EXPANSÃO",
            "title": "Carvalho Super inaugura nova loja no Riverside Shopping",
            "date": "2026-08-10"
        }
        e2 = {
            "entity": self.empresa, "kind": "EXPANSÃO",
            "title": "Carvalho Super abre nova loja no Riverside Shopping",
            "date": "2026-08-10"
        }
        self.assertTrue(sniper.eventos_sao_mesmo_fato(e1, e2))

        # Eventos com temas distintos -> não são o mesmo fato
        e3 = {
            "entity": self.empresa, "kind": "PESSOAS",
            "title": "Carvalho contrata 100 profissionais em Teresina",
            "date": "2026-08-10"
        }
        self.assertFalse(sniper.eventos_sao_mesmo_fato(e1, e3))

        # Eventos com títulos semelhantes mas datas distantes (>45 dias) -> não agrupam
        e4 = {
            "entity": self.empresa, "kind": "EXPANSÃO",
            "title": "Carvalho Super inaugura nova loja no Riverside Shopping",
            "date": "2025-01-10"
        }
        self.assertFalse(sniper.eventos_sao_mesmo_fato(e1, e4))

    def test_04_criar_eventos_agrupamento_sintetico(self):
        """Testa clustering completo de lista de fontes em eventos consolidados."""
        f1 = sniper.Fonte(
            id=1, titulo="Carvalho Super inaugura nova loja no bairro Jockey",
            url="https://portal1.com/noticia1", origem="web",
            conteudo="Inauguração de supermercado em Teresina",
            data_publicacao="2026-08-12", alias_empresa=self.empresa,
            cidade_confirmada=True, estado_confirmado=True, escopo="local",
            entidade=self.empresa, score=85.0
        )
        f2 = sniper.Fonte(
            id=2, titulo="Carvalho Super abre nova loja no bairro Jockey",
            url="https://portal2.com/noticia2", origem="web",
            conteudo="Abertura de supermercado em Teresina",
            data_publicacao="2026-08-12", alias_empresa=self.empresa,
            cidade_confirmada=True, estado_confirmado=True, escopo="local",
            entidade=self.empresa, score=80.0
        )
        f3 = sniper.Fonte(
            id=3, titulo="Concorrente Mateus abre vagas de emprego em Teresina",
            url="https://portal3.com/noticia3", origem="web",
            conteudo="Processo seletivo para 50 vagas no atacarejo",
            data_publicacao="2026-08-14", alias_empresa="",
            cidade_confirmada=True, estado_confirmado=True, escopo="local",
            entidade="Mateus", score=75.0
        )

        eventos = sniper.criar_eventos([f1, f2, f3])
        self.assertIsInstance(eventos, list)
        self.assertGreaterEqual(len(eventos), 2)

        # O evento de expansão deve ter agrupado f1 e f2 (2 fontes correlatas)
        evt_expansao = next((e for e in eventos if e.get("kind") == "EXPANSÃO"), None)
        self.assertIsNotNone(evt_expansao)
        self.assertIn(1, evt_expansao["evidence_ids"])
        self.assertIn(2, evt_expansao["evidence_ids"])
        self.assertGreaterEqual(evt_expansao["independent_source_count"], 2)


if __name__ == "__main__":
    unittest.main()
