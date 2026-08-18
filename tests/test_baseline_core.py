# -*- coding: utf-8 -*-
"""
Testes de Baseline de Regressão — Agente Sniper v11.8.0
Verifica o comportamento das funções puras, normalizações, filtros e algoritmos.
"""
import sys
import unittest
from pathlib import Path

# Adiciona raiz ao sys.path para permitir importação padrão
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import agente_sniper_v11_8 as sniper


class TestBaselineCore(unittest.TestCase):

    def test_01_versao_e_importacao_segura(self):
        """Confirma que o motor v11.8 foi importado com segurança e possui versão correta."""
        self.assertEqual(sniper.APP_VERSION, "11.8.0")
        self.assertTrue(callable(sniper.main))
        self.assertIsNotNone(sniper.Fonte)
        self.assertIsNotNone(sniper.PriceItem)
        self.assertIsNotNone(sniper.MemoriaSniper)

    def test_02_normalizar(self):
        """Testa normalização NFKD, remoção de acentos e case folding."""
        self.assertEqual(sniper.normalizar("Áçúcar Cristal"), "acucar cristal")
        self.assertEqual(sniper.normalizar("  SUPERMERCADO   CARVALHO  "), "supermercado carvalho")
        self.assertEqual(sniper.normalizar(None), "")
        self.assertEqual(sniper.normalizar(123), "123")

    def test_03_remover_acentos(self):
        """Testa sanitização Latin-1 compatível com FPDF Helvetica."""
        texto_in = "Relatório — Preço de “Café” & Chá • Promoção"
        texto_out = sniper.remover_acentos(texto_in)
        self.assertNotIn("“", texto_out)
        self.assertNotIn("”", texto_out)
        self.assertNotIn("—", texto_out)
        self.assertNotIn("•", texto_out)
        # Deve decodificar perfeitamente em latin-1
        texto_out.encode("latin-1")

    def test_04_termo(self):
        """Testa boundary check de termos exatos."""
        self.assertTrue(sniper.termo("Supermercado Carvalho Teresina", "Carvalho"))
        self.assertTrue(sniper.termo("supermercado carvalho", "carvalho"))
        # Boundary match: 'carvalhos' não deve bater com 'carvalho'
        self.assertFalse(sniper.termo("supermercados carvalhos", "carvalho"))
        self.assertFalse(sniper.termo("", "carvalho"))
        self.assertFalse(sniper.termo("texto qualquer", ""))

    def test_05_url_normalizada(self):
        """Testa limpeza de parâmetros de rastreamento e padronização de URLs."""
        url_suja = "https://www.loja.com.br/produtos/arroz/?utm_source=google&utm_medium=cpc&gclid=12345&id=99"
        url_limpa = sniper.url_normalizada(url_suja)
        self.assertEqual(url_limpa, "https://loja.com.br/produtos/arroz?id=99")
        self.assertNotIn("utm_source", url_limpa)
        self.assertNotIn("gclid", url_limpa)
        self.assertNotIn("www.", url_limpa)

    def test_06_dominio(self):
        """Testa extração de domínio sem www."""
        self.assertEqual(sniper.dominio("https://www.carvalhosupershop.com.br/catalogo"), "carvalhosupershop.com.br")
        self.assertEqual(sniper.dominio("http://g1.globo.com/pi/noticia"), "g1.globo.com")
        self.assertEqual(sniper.dominio("invalido"), "")

    def test_07_sha1(self):
        """Testa geração de hash SHA-1 determinístico."""
        h1 = sniper.sha1("teste_sniper_2026")
        h2 = sniper.sha1("teste_sniper_2026")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 40)

    def test_08_parse_money(self):
        """Testa parsing de valores monetários no formato brasileiro."""
        self.assertEqual(sniper.parse_money("R$ 1.290,50"), 1290.50)
        self.assertEqual(sniper.parse_money("1290,50"), 1290.50)
        self.assertEqual(sniper.parse_money("R$ 9,99"), 9.99)
        self.assertEqual(sniper.parse_money("7.99"), 7.99)
        self.assertEqual(sniper.parse_money("0,00"), 0.0)
        self.assertIsNone(sniper.parse_money(None))
        self.assertIsNone(sniper.parse_money(""))
        self.assertIsNone(sniper.parse_money("sem preco"))

    def test_09_normalizar_quantidade(self):
        """Testa equivalência de unidades de medida."""
        self.assertEqual(sniper.normalizar_quantidade("1kg"), (1000.0, "g"))
        self.assertEqual(sniper.normalizar_quantidade("500g"), (500.0, "g"))
        self.assertEqual(sniper.normalizar_quantidade("1.5 kg"), (1500.0, "g"))
        self.assertEqual(sniper.normalizar_quantidade("1 l"), (1000.0, "ml"))
        self.assertEqual(sniper.normalizar_quantidade("200 ml"), (200.0, "ml"))
        self.assertEqual(sniper.normalizar_quantidade("2 un"), (2.0, "un"))
        self.assertEqual(sniper.normalizar_quantidade("invalido"), (None, None))

    def test_10_score_clamp(self):
        """Testa limitação estrita de scores entre 0 e 100."""
        self.assertEqual(sniper.score_clamp(-15.5), 0)
        self.assertEqual(sniper.score_clamp(150.0), 100)
        self.assertEqual(sniper.score_clamp(75.4), 75)
        self.assertEqual(sniper.score_clamp(75.6), 76)

    def test_11_identidade_conflitante(self):
        """Testa rejeição de homônimos de ferramentas e materiais de construção."""
        self.assertTrue(sniper.identidade_conflitante("M Carvalho & Cia Ltda - loja de ferramentas em Teresina"))
        self.assertTrue(sniper.identidade_conflitante("Carvalho Material de Construcao"))
        self.assertFalse(sniper.identidade_conflitante("Supermercado Carvalho ofertas e precos"))
        self.assertFalse(sniper.identidade_conflitante("Grupo Carvalho abre vagas no varejo"))

    def test_12_cidade_e_estado_ok(self):
        """Testa confirmação de localidade geográfica baseada no .env (Teresina-PI)."""
        self.assertTrue(sniper.cidade_ok("Supermercado em Teresina com promocoes"))
        self.assertFalse(sniper.cidade_ok("Supermercado em Fortaleza CE"))
        self.assertTrue(sniper.estado_ok("Varejo alimentar no estado do PI"))
        self.assertTrue(sniper.estado_ok("Supermercado Carvalho PI"))
        self.assertFalse(sniper.estado_ok("Supermercado em Fortaleza CE"))

    def test_13_similaridade_produto(self):
        """Testa o algoritmo fuzzy de similaridade de produtos e precificação."""
        p_alvo = sniper.PriceItem(
            source="Carvalho",
            role="target",
            name="Arroz Tio João Parboilizado 1kg",
            url="https://alvo.com/arroz",
            price=7.99,
            brand="Tio João",
            unit="1kg",
            sku="SKU123"
        )
        p_match = sniper.PriceItem(
            source="Mateus",
            role="competitor",
            name="Arroz Tio João Parbo 1000g",
            url="https://concorrente.com/arroz",
            price=7.49,
            brand="Tio João",
            unit="1000g",
            sku="SKU123"
        )
        p_diferente = sniper.PriceItem(
            source="Mateus",
            role="competitor",
            name="Sabão em Pó Omo Lavagem Perfeita 1kg",
            url="https://concorrente.com/omo",
            price=16.90,
            brand="Omo",
            unit="1kg",
            sku="SKU999"
        )
        # Produtos equivalentes com mesma marca, SKU e peso convertido devem ter similaridade alta (>= 0.90)
        sim_alta = sniper.similaridade_produto(p_alvo, p_match)
        self.assertGreaterEqual(sim_alta, 0.90)

        # Produtos de categorias completamente diferentes devem ter similaridade baixa (< 0.35)
        sim_baixa = sniper.similaridade_produto(p_alvo, p_diferente)
        self.assertLess(sim_baixa, 0.35)

    def test_14_canonical_event_key(self):
        """Testa geração de chave canônica estável para clustering de eventos."""
        f1 = sniper.Fonte(
            id=1,
            titulo="Carvalho Super inaugura nova unidade no Riverside Shopping em Teresina",
            url="https://noticia1.com/inauguracao",
            origem="web",
            conteudo="Inauguração de loja",
            data_publicacao="2026-08-10",
            alias_empresa="Carvalho",
            cidade_confirmada=True,
            estado_confirmado=True,
            escopo="local",
            entidade="Carvalho"
        )
        key = sniper.canonical_event_key(f1, "EXPANSÃO")
        self.assertIsInstance(key, str)
        self.assertEqual(len(key), 24)

    def test_15_validar_ids_sinais(self):
        """Testa o validador anti-alucinação de IDs de evidência."""
        ids_validos = {1, 2, 3, 4, 5}

        pacote_valido = {
            "sinais": [
                {"titulo": "Sinal 1", "evidence_ids": [1, 2]},
                {"titulo": "Sinal 2", "evidence_ids": [3]}
            ],
            "concorrencia": [
                {"nome": "Mateus", "evidence_ids": [4, 5]}
            ]
        }
        ok, reason = sniper.validar_ids_sinais(pacote_valido, ids_validos)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

        pacote_invalido = {
            "sinais": [
                {"titulo": "Sinal Alucinado", "evidence_ids": [1, 999]}
            ]
        }
        ok_inv, reason_inv = sniper.validar_ids_sinais(pacote_invalido, ids_validos)
        self.assertFalse(ok_inv)
        self.assertIn("999", reason_inv)


if __name__ == "__main__":
    unittest.main()
