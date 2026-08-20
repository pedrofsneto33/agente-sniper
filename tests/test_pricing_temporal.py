# -*- coding: utf-8 -*-
"""
Suíte de Testes Formais para Séries Temporais e Inteligência de Preços (Fase 33 / Etapa 2).
Cobre 16 cenários formais:
1. Lista vazia -> {}
2. Um único ponto (métricas de base, preco_anterior=None, volatilidade=0.0, tendencia=INSUFICIENTE)
3. Cinco pontos estáveis (deltas=0.0, volatilidade=0.0, tendencia=ESTAVEL)
4. Série em alta (deltas positivos, tendencia=ALTA)
5. Série em queda (deltas negativos, tendencia=QUEDA)
6. Preços inválidos (None, zero, negativos, strings não-numéricas descartados)
7. Múltiplos produtos e entidades (agrupamento correto por chave tupla)
8. Timestamps fora de ordem (ordenação determinística)
9. Desvio padrão amostral com resultado analiticamente conhecido
10. Janela sem observação histórica válida (delta_janela=None)
11. Múltiplas observações dentro da mesma janela (seleção da base mais antiga na janela)
12. Determinismo estrito (10 execuções com payload completo idêntico)
13. Imutabilidade absoluta das entradas
14. Timestamps iguais com desempate determinístico
15. Ponto exatamente no limite da janela (limite_inicio <= data <= ref)
16. Invariância à permutação da ordem de entrada
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.pricing import calcular_serie_temporal_precos


class TestPricingTemporal(unittest.TestCase):
    """Testes unitários formais para cálculo de séries temporais de preços e métricas de mercado."""

    def setUp(self):
        self.hoje_fixo = datetime(2026, 8, 20)

    def test_01_lista_vazia(self):
        """1. Lista vazia de snapshots retorna dicionário vazio."""
        res = calcular_serie_temporal_precos([], hoje=self.hoje_fixo)
        self.assertEqual(res, {})

    def test_02_unico_ponto(self):
        """2. Um único ponto retorna métricas iniciais com anterior e deltas nulos e tendência INSUFICIENTE."""
        s1 = {
            "entity": "Mateus", "source_domain": "mateusmais.com.br", "product_key": "arroz_1kg",
            "product_name": "Arroz Tio João 1kg", "brand": "Tio João", "unit": "kg",
            "price": 10.0, "promotion": False, "captured_at": "2026-08-20T08:00:00"
        }
        res = calcular_serie_temporal_precos([s1], hoje=self.hoje_fixo)
        key = ("Mateus", "mateusmais.com.br", "arroz_1kg")
        self.assertIn(key, res)
        serie = res[key]
        self.assertEqual(serie["preco_atual"], 10.0)
        self.assertIsNone(serie["preco_anterior"])
        self.assertIsNone(serie["variacao_imediata_pct"])
        self.assertEqual(serie["preco_min"], 10.0)
        self.assertEqual(serie["preco_max"], 10.0)
        self.assertEqual(serie["media_preco"], 10.0)
        self.assertEqual(serie["volatilidade"], 0.0)
        self.assertEqual(serie["tendencia"], "INSUFICIENTE")
        self.assertEqual(serie["pontos_observados"], 1)
        self.assertEqual(serie["deltas_janela"], {7: None, 15: None, 30: None})

    def test_03_cinco_pontos_estaveis(self):
        """3. Cinco pontos idênticos ao longo de 30 dias geram deltas 0.0, volatilidade 0.0 e ESTAVEL."""
        datas = ["2026-07-21", "2026-07-30", "2026-08-06", "2026-08-14", "2026-08-20"]
        snapshots = [
            {
                "entity": "Mateus", "source_domain": "mateusmais.com.br", "product_key": "feijao_1kg",
                "product_name": "Feijão Preto 1kg", "brand": "Camil", "unit": "kg",
                "price": 8.0, "promotion": False, "captured_at": d
            }
            for d in datas
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Mateus", "mateusmais.com.br", "feijao_1kg")
        serie = res[key]
        self.assertEqual(serie["preco_atual"], 8.0)
        self.assertEqual(serie["preco_anterior"], 8.0)
        self.assertEqual(serie["variacao_imediata_pct"], 0.0)
        self.assertEqual(serie["volatilidade"], 0.0)
        self.assertEqual(serie["tendencia"], "ESTAVEL")
        self.assertEqual(serie["pontos_observados"], 5)
        self.assertEqual(serie["deltas_janela"][7], 0.0)
        self.assertEqual(serie["deltas_janela"][15], 0.0)
        self.assertEqual(serie["deltas_janela"][30], 0.0)

    def test_04_serie_em_alta(self):
        """4. Série com aumentos graduais ao longo de 30 dias resulta em deltas positivos e tendência ALTA."""
        snapshots = [
            {"entity": "Mateus", "source_domain": "mateusmais.com.br", "product_key": "oleo_900ml", "price": 5.00, "captured_at": "2026-07-21"},
            {"entity": "Mateus", "source_domain": "mateusmais.com.br", "product_key": "oleo_900ml", "price": 5.50, "captured_at": "2026-08-05"},
            {"entity": "Mateus", "source_domain": "mateusmais.com.br", "product_key": "oleo_900ml", "price": 6.00, "captured_at": "2026-08-20"},
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Mateus", "mateusmais.com.br", "oleo_900ml")
        serie = res[key]
        self.assertEqual(serie["preco_atual"], 6.00)
        self.assertEqual(serie["preco_anterior"], 5.50)
        self.assertEqual(serie["variacao_imediata_pct"], 9.09)
        self.assertEqual(serie["preco_min"], 5.00)
        self.assertEqual(serie["preco_max"], 6.00)
        self.assertEqual(serie["tendencia"], "ALTA")
        self.assertEqual(serie["deltas_janela"][30], 20.0)  # (6.0 - 5.0) / 5.0 * 100

    def test_05_serie_em_queda(self):
        """5. Série com reduções de preço resulta em deltas negativos e tendência QUEDA."""
        snapshots = [
            {"entity": "Mateus", "source_domain": "mateusmais.com.br", "product_key": "cafe_500g", "price": 20.00, "captured_at": "2026-07-21"},
            {"entity": "Mateus", "source_domain": "mateusmais.com.br", "product_key": "cafe_500g", "price": 18.00, "captured_at": "2026-08-05"},
            {"entity": "Mateus", "source_domain": "mateusmais.com.br", "product_key": "cafe_500g", "price": 16.00, "captured_at": "2026-08-20"},
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Mateus", "mateusmais.com.br", "cafe_500g")
        serie = res[key]
        self.assertEqual(serie["preco_atual"], 16.00)
        self.assertEqual(serie["preco_anterior"], 18.00)
        self.assertEqual(serie["variacao_imediata_pct"], -11.11)
        self.assertEqual(serie["tendencia"], "QUEDA")
        self.assertEqual(serie["deltas_janela"][30], -20.0)

    def test_06_precos_invalidos_descartados(self):
        """6. Valores None, zero, negativos e strings inválidas são descartados sem quebrar a série."""
        snapshots = [
            {"entity": "Carvalho", "source_domain": "carvalho.com.br", "product_key": "leite_1l", "price": None, "captured_at": "2026-08-01"},
            {"entity": "Carvalho", "source_domain": "carvalho.com.br", "product_key": "leite_1l", "price": 0.0, "captured_at": "2026-08-02"},
            {"entity": "Carvalho", "source_domain": "carvalho.com.br", "product_key": "leite_1l", "price": -5.0, "captured_at": "2026-08-03"},
            {"entity": "Carvalho", "source_domain": "carvalho.com.br", "product_key": "leite_1l", "price": "invalido", "captured_at": "2026-08-04"},
            {"entity": "Carvalho", "source_domain": "carvalho.com.br", "product_key": "leite_1l", "price": 4.50, "captured_at": "2026-08-10"},
            {"entity": "Carvalho", "source_domain": "carvalho.com.br", "product_key": "leite_1l", "price": 5.00, "captured_at": "2026-08-20"},
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Carvalho", "carvalho.com.br", "leite_1l")
        self.assertIn(key, res)
        serie = res[key]
        self.assertEqual(serie["pontos_observados"], 2)
        self.assertEqual(serie["preco_atual"], 5.00)
        self.assertEqual(serie["preco_anterior"], 4.50)

    def test_07_multiplos_produtos_e_entidades(self):
        """7. Agrupa estritamente por (entity, source_domain, product_key) sem misturar catálogos."""
        snapshots = [
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "arroz", "price": 5.0, "captured_at": "2026-08-20"},
            {"entity": "Carvalho", "source_domain": "carvalho.com", "product_key": "arroz", "price": 5.2, "captured_at": "2026-08-20"},
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "feijao", "price": 7.0, "captured_at": "2026-08-20"},
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        self.assertEqual(len(res), 3)
        self.assertIn(("Mateus", "mateus.com", "arroz"), res)
        self.assertIn(("Carvalho", "carvalho.com", "arroz"), res)
        self.assertIn(("Mateus", "mateus.com", "feijao"), res)

    def test_08_timestamps_fora_de_ordem(self):
        """8. Snapshots fornecidos fora de ordem cronológica são ordenados deterministicamente."""
        snapshots = [
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "acucar", "price": 4.0, "captured_at": "2026-08-20"},
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "acucar", "price": 3.0, "captured_at": "2026-08-01"},
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "acucar", "price": 3.5, "captured_at": "2026-08-10"},
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Mateus", "mateus.com", "acucar")
        serie = res[key]
        self.assertEqual(serie["preco_atual"], 4.0)
        self.assertEqual(serie["preco_anterior"], 3.5)
        datas = [pt["data"] for pt in serie["serie_historica"]]
        self.assertEqual(datas, ["2026-08-01", "2026-08-10", "2026-08-20"])

    def test_09_desvio_padrao_amostral(self):
        """9. Volatilidade é calculada como o desvio padrão amostral s exato."""
        # Valores: [10, 12, 14, 16, 18], N=5, média=14
        # Variância = sum((x-14)^2) / 4 = (16+4+0+4+16)/4 = 40/4 = 10.0
        # s = sqrt(10.0) ≈ 3.162277... -> 3.1623
        precos = [10.0, 12.0, 14.0, 16.0, 18.0]
        snapshots = [
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "sal", "price": p, "captured_at": f"2026-08-0{i+1}"}
            for i, p in enumerate(precos)
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Mateus", "mateus.com", "sal")
        self.assertAlmostEqual(res[key]["volatilidade"], 3.1623, places=4)

    def test_10_janela_sem_observacao_valida(self):
        """10. Janela temporal sem pontos intermediários válidos retorna None para aquele delta."""
        snapshots = [
            # Ponto de 50 dias atrás (fora das janelas 7, 15, 30) e ponto atual
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "farinha", "price": 4.0, "captured_at": "2026-06-25"},
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "farinha", "price": 5.0, "captured_at": "2026-08-20"},
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Mateus", "mateus.com", "farinha")
        serie = res[key]
        self.assertIsNone(serie["deltas_janela"][7])
        self.assertIsNone(serie["deltas_janela"][15])
        self.assertIsNone(serie["deltas_janela"][30])

    def test_11_multiplas_observacoes_na_mesma_janela(self):
        """11. Múltiplas observações dentro da janela: usa a base mais antiga na janela."""
        snapshots = [
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "macarrao", "price": 3.0, "captured_at": "2026-08-14"}, # 6d atrás
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "macarrao", "price": 3.5, "captured_at": "2026-08-18"}, # 2d atrás
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "macarrao", "price": 4.0, "captured_at": "2026-08-20"}, # atual
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Mateus", "mateus.com", "macarrao")
        serie = res[key]
        # Janela 7d inclui 2026-08-14 (p_base=3.0). Delta = (4.0 - 3.0) / 3.0 * 100 = +33.33%
        self.assertEqual(serie["deltas_janela"][7], 33.33)
        self.assertEqual(serie["preco_anterior"], 3.5)

    def test_12_determinismo_estrito(self):
        """12. 10 execuções produzem payload estruturalmente idêntico."""
        snapshots = [
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "massa", "price": 3.0, "captured_at": "2026-08-01"},
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "massa", "price": 3.5, "captured_at": "2026-08-10"},
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "massa", "price": 4.0, "captured_at": "2026-08-20"},
        ]
        runs = [calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo) for _ in range(10)]
        for r in runs:
            self.assertEqual(r, runs[0])

    def test_13_imutabilidade_das_entradas(self):
        """13. A função não muta os dicionários nem listas de entrada."""
        s = {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "sal", "price": 2.0, "captured_at": "2026-08-20"}
        copia = dict(s)
        calcular_serie_temporal_precos([s], hoje=self.hoje_fixo)
        self.assertEqual(s, copia)

    def test_14_timestamps_iguais_desempate_deterministico(self):
        """14. Observações com mesmo timestamp são ordenadas deterministicamente por preço/url."""
        snapshots = [
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "suco", "price": 6.0, "url": "https://a.com", "captured_at": "2026-08-20"},
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "suco", "price": 5.0, "url": "https://b.com", "captured_at": "2026-08-20"},
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Mateus", "mateus.com", "suco")
        serie = res[key]
        self.assertEqual(serie["preco_min"], 5.0)
        self.assertEqual(serie["preco_max"], 6.0)
        self.assertEqual(serie["preco_atual"], 6.0)
        self.assertEqual(serie["preco_anterior"], 5.0)

    def test_15_ponto_no_limite_exato_da_janela(self):
        """15. Ponto exatamente a W dias de hoje (ex: hoje - 7d) é incluído na janela."""
        # hoje = 2026-08-20. 7 dias atrás = 2026-08-13
        snapshots = [
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "queijo", "price": 20.0, "captured_at": "2026-08-13"},
            {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "queijo", "price": 22.0, "captured_at": "2026-08-20"},
        ]
        res = calcular_serie_temporal_precos(snapshots, hoje=self.hoje_fixo)
        key = ("Mateus", "mateus.com", "queijo")
        self.assertEqual(res[key]["deltas_janela"][7], 10.0)

    def test_16_invariancia_ordem_de_entrada(self):
        """16. O resultado final é idêntico independentemente da ordem da lista de entrada."""
        s1 = {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "presunto", "price": 10.0, "captured_at": "2026-08-01"}
        s2 = {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "presunto", "price": 11.0, "captured_at": "2026-08-10"}
        s3 = {"entity": "Mateus", "source_domain": "mateus.com", "product_key": "presunto", "price": 12.0, "captured_at": "2026-08-20"}
        res_ord = calcular_serie_temporal_precos([s1, s2, s3], hoje=self.hoje_fixo)
        res_inv = calcular_serie_temporal_precos([s3, s1, s2], hoje=self.hoje_fixo)
        self.assertEqual(res_ord, res_inv)


if __name__ == "__main__":
    unittest.main()
