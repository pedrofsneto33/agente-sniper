# -*- coding: utf-8 -*-
"""
Suíte de Testes Unitários para o Pacote search/ (Fase 38).
Testa:
1. TavilyBudgetGuard: inicialização, contadores atômicos, bloqueio de budget e cache TTL de 24h.
2. TavilyBudgetGuard (Circuit Breaker): abertura automática sob erros 429, quota e rate limit.
3. gerar_consultas: geração parametrizada multi-nicho e estrutura de categorias.
4. buscar_ddg: extração de campos e fallback controlado sem exceções.
5. buscar_news_rss: parsing XML/RSS com entidades HTML e fallback gracioso.
6. coletar_tudo: execução concorrente com ordenação canônica determinística rigorosa.
7. search.__all__: conformidade formal dos símbolos exportados na API pública.
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import search
from search import (
    TavilyBudgetGuard,
    buscar_ddg,
    buscar_news_rss,
    buscar_tavily,
    coletar_tudo,
    gerar_consultas,
)


class TestSearchModule(unittest.TestCase):
    """Testes unitários isolados do pacote search sem conexões reais de rede."""

    def test_01_tavily_budget_guard_lifecycle(self):
        """1. Valida ciclo de vida, contadores atômicos, budget guard e cache hit."""
        guard = TavilyBudgetGuard(max_queries=2)
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [{"title": "Artigo 1", "url": "https://a.com/1", "content": "Conteúdo 1", "published_date": "2026-08-01"}]
        }

        # Primeira query: executa normalmente
        r1 = guard.search(mock_client, "supermercado teresina", "noticia")
        self.assertEqual(len(r1), 1)
        self.assertEqual(guard.queries_attempted, 1)
        self.assertEqual(guard.queries_executed, 1)
        self.assertEqual(guard.cache_hits, 0)
        self.assertEqual(guard.estimated_credits_used, 1)

        # Segunda query idêntica: deve vir do cache (cache hit)
        r2 = guard.search(mock_client, "supermercado teresina", "noticia")
        self.assertEqual(len(r2), 1)
        self.assertEqual(guard.queries_attempted, 2)
        self.assertEqual(guard.queries_executed, 1)
        self.assertEqual(guard.cache_hits, 1)

        # Terceira query (diferente): executa até atingir o budget max=2
        guard.search(mock_client, "outra query", "mercado")
        self.assertEqual(guard.queries_executed, 2)

        # Quarta query (diferente): deve ser bloqueada pelo budget
        r4 = guard.search(mock_client, "terceira query bloqueada", "mercado")
        self.assertEqual(r4, [])
        self.assertEqual(guard.queries_blocked_budget, 1)
        self.assertEqual(guard.queries_executed, 2)

    def test_02_tavily_circuit_breaker(self):
        """2. Valida abertura automática do circuit breaker sob HTTP 429 ou quota limit."""
        guard = TavilyBudgetGuard(max_queries=10)
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("HTTP 429 Too Many Requests: Rate limit exceeded")

        res1 = guard.search(mock_client, "query falha", "noticia")
        self.assertEqual(res1, [])
        self.assertTrue(guard.circuit_open)
        self.assertIn("429", guard.circuit_reason)

        # Chamadas subsequentes devem ser abortadas imediatamente
        res2 = guard.search(mock_client, "outra query", "noticia")
        self.assertEqual(res2, [])
        self.assertEqual(guard.failures, 1)

    def test_03_gerar_consultas_multiniche(self):
        """3. Valida geração de consultas multi-nicho e injeção contextual."""
        consultas = gerar_consultas(
            empresa_alvo="Hospital Santa Maria",
            cidade="Teresina",
            estado="PI",
            nicho="saúde",
            concorrentes=["Hospital Alfa", "Clínica Beta"],
            queries_nicho=["leitos", "urgência", "convênios"],
            ano=2026,
        )
        self.assertIn("empresa", consultas)
        self.assertIn("concorrencia", consultas)
        self.assertIn("comercial", consultas)
        self.assertIn("mercado", consultas)

        # Verifica queries geradas com nicho saúde
        queries_emp = [q for q, _ in consultas["empresa"]]
        self.assertTrue(any("leitos" in q for q in queries_emp))
        self.assertTrue(any("Hospital Santa Maria" in q for q in queries_emp))

        queries_merc = [q for q, _ in consultas["mercado"]]
        self.assertTrue(any("saúde" in q for q in queries_merc))

    @patch("search.providers.DDGS")
    def test_04_buscar_ddg_mock(self, mock_ddgs_cls):
        """4. Valida parsing de resultados e fallback do DuckDuckGo."""
        mock_instance = MagicMock()
        mock_instance.text.return_value = [
            {"title": "Notícia DDG", "href": "https://ddg.com/1", "body": "Resumo DDG"}
        ]
        mock_ddgs_cls.return_value.__enter__.return_value = mock_instance

        res = buscar_ddg("query teste", "noticia")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["titulo"], "Notícia DDG")
        self.assertEqual(res[0]["origem"], "DuckDuckGo")

        # Teste quando DDGS lança exceção
        mock_instance.text.side_effect = Exception("DDG timeout")
        self.assertEqual(buscar_ddg("query erro", "noticia"), [])

    @patch("requests.Session.get")
    def test_05_buscar_news_rss_mock(self, mock_get):
        """5. Valida parsing XML de RSS com remoção de tags HTML na descrição."""
        xml_sample = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Google News</title>
            <item>
              <title>Supermercado expande em Teresina</title>
              <link>https://news.google.com/articles/123</link>
              <description>&lt;p&gt;Texto com &lt;b&gt;tags html&lt;/b&gt;&lt;/p&gt;</description>
              <pubDate>Thu, 20 Aug 2026 10:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""
        mock_resp = MagicMock()
        mock_resp.text = xml_sample
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        res = buscar_news_rss("query rss", "noticia")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["titulo"], "Supermercado expande em Teresina")
        self.assertEqual(res[0]["conteudo"], "Texto com tags html")
        self.assertEqual(res[0]["origem"], "Google News RSS")

        # Teste quando requests falha
        mock_get.side_effect = Exception("Connection error")
        self.assertEqual(buscar_news_rss("query erro", "noticia"), [])

    def test_06_coletar_tudo_deterministic_order(self):
        """6. Valida que coletar_tudo reconstitui os resultados em ordem canônica estrita."""
        consultas_fake = {
            "empresa": [("query_0", "Empresa A"), ("query_1", "Empresa A")],
        }

        # Mock das funções individuais com latências e retornos estruturados
        def fake_tavily(client, q, cat, guard=None):
            time.sleep(0.01 if "0" in q else 0.001)
            return [{"titulo": f"tavily_{q}", "url": f"https://t.com/{q}", "conteudo": "", "origem": "Tavily", "data_publicacao": "", "categoria": cat}]

        def fake_ddg(q, cat):
            time.sleep(0.005 if "0" in q else 0.02)
            return [{"titulo": f"ddg_{q}", "url": f"https://d.com/{q}", "conteudo": "", "origem": "DuckDuckGo", "data_publicacao": "", "categoria": cat}]

        def fake_rss(q, cat, session=None):
            return [{"titulo": f"rss_{q}", "url": f"https://r.com/{q}", "conteudo": "", "origem": "Google News RSS", "data_publicacao": "", "categoria": cat}]

        with patch("search.providers.buscar_tavily", side_effect=fake_tavily),              patch("search.providers.buscar_ddg", side_effect=fake_ddg),              patch("search.providers.buscar_news_rss", side_effect=fake_rss):

            res = coletar_tudo(
                tavily_client=MagicMock(),
                consultas=consultas_fake,
                max_consultas_por_grupo=2,
                usar_tavily=True,
                usar_ddg=True,
                usar_news_rss=True,
                max_workers=4,
            )

            # Ordem canônica esperada:
            # q_id 0: tavily_query_0, ddg_query_0, rss_query_0
            # q_id 1: tavily_query_1, ddg_query_1, rss_query_1
            titulos = [x["titulo"] for x in res]
            expected = [
                "tavily_query_0", "ddg_query_0", "rss_query_0",
                "tavily_query_1", "ddg_query_1", "rss_query_1",
            ]
            self.assertEqual(titulos, expected)
            for item in res:
                self.assertEqual(item["alvo"], "Empresa A")

    def test_07_search_public_api_exports(self):
        """7. Valida exportações públicas do pacote search."""
        expected = [
            "TavilyBudgetGuard",
            "gerar_consultas",
            "buscar_tavily",
            "buscar_ddg",
            "buscar_news_rss",
            "coletar_tudo",
        ]
        self.assertEqual(set(search.__all__), set(expected))
        for sym in expected:
            self.assertTrue(hasattr(search, sym), f"Missing symbol {sym} on search package")


if __name__ == "__main__":
    unittest.main()
