# -*- coding: utf-8 -*-
"""
Suíte de Testes Unitários para o Pacote web/ (Fase 39).
Testa:
1. PersistentPlaywrightManager: inicialização segura, ciclo de vida, contadores e fallback sem crash.
2. extrair_html: extração HTTP síncrona com headers e timeout mockado.
3. extrair_pagina (metadados e JSON-LD): parsing de title, meta article:published_time e script application/ld+json.
4. extrair_pagina (fallback para Playwright): disparo de fallback quando o texto HTML tem < 250 caracteres.
5. enriquecer: execução concorrente com ordenação e re-scoring canônico determinístico de instâncias Fonte.
6. web.__all__: conformidade estrita da API pública exportada.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import web
from domain.models import Fonte
from web import (
    PersistentPlaywrightManager,
    enriquecer,
    extrair_html,
    extrair_pagina,
    extrair_playwright,
)


class TestWebModule(unittest.TestCase):
    """Testes unitários isolados do pacote web sem conexões reais de rede ou browsers reais."""

    def test_01_playwright_manager_lifecycle_and_fallback(self):
        """1. Valida ciclo de vida do PersistentPlaywrightManager quando inativo ou indisponível."""
        # Instância inativa: get_browser() deve retornar None graciosamente
        mgr_inactive = PersistentPlaywrightManager(ativo=False)
        self.assertIsNone(mgr_inactive.get_browser())
        self.assertIsNone(mgr_inactive.new_isolated_context())
        self.assertIsNone(mgr_inactive.extrair_pagina_playwright("https://example.com"))

        # Instância ativa com mock de sync_playwright
        mgr = PersistentPlaywrightManager(ativo=True)
        with patch.dict("sys.modules", {"playwright.sync_api": MagicMock()}):
            mock_pw_module = sys.modules["playwright.sync_api"]
            mock_pw_instance = MagicMock()
            mock_browser = MagicMock()
            mock_pw_module.sync_playwright.return_value.start.return_value = mock_pw_instance
            mock_pw_instance.chromium.launch.return_value = mock_browser

            browser = mgr.get_browser()
            self.assertEqual(browser, mock_browser)
            self.assertEqual(mgr.launch_count, 1)

            # Extração de página mockada
            mock_context = MagicMock()
            mock_page = MagicMock()
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            mock_page.locator.return_value.inner_text.return_value = "Conteúdo renderizado via Playwright"
            mock_page.title.return_value = "Título Playwright"
            mock_page.url = "https://example.com/final"

            res = mgr.extrair_pagina_playwright("https://example.com", timeout=1000)
            self.assertIsNotNone(res)
            self.assertEqual(res["conteudo"], "Conteúdo renderizado via Playwright")
            self.assertEqual(res["titulo"], "Título Playwright")
            self.assertEqual(mgr.success_count, 1)

            # Fechamento
            mgr.close_all()
            self.assertIsNone(mgr._browser)
            self.assertFalse(mgr._initialized)

    @patch("requests.Session.get")
    def test_02_extrair_html_mock(self, mock_get):
        """2. Valida extração HTTP síncrona com retorno estruturado."""
        mock_resp = MagicMock()
        mock_resp.text = "<html><head><title>Página Teste</title></head><body>Texto</body></html>"
        mock_resp.url = "https://exemplo.com.br/artigo"
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        res = extrair_html("https://exemplo.com.br/artigo")
        self.assertIn("Página Teste", res["html"])
        self.assertEqual(res["final_url"], "https://exemplo.com.br/artigo")
        self.assertEqual(res["content_type"], "text/html; charset=utf-8")

    @patch("web.extractor.extrair_html")
    def test_03_extrair_pagina_json_ld_and_meta(self, mock_extrair_html):
        """3. Valida extração de texto, tags meta e dados estruturados JSON-LD."""
        html_content = """
        <html>
          <head>
            <title>Notícia Comercial</title>
            <meta property="article:published_time" content="2026-08-20T10:00:00Z">
            <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "NewsArticle",
              "headline": "Supermercado Abre Nova Filial",
              "datePublished": "2026-08-20T10:00:00Z"
            }
            </script>
          </head>
          <body>
            <p>O Supermercado Carvalho inaugurou nesta quinta-feira uma nova loja moderna na zona leste de Teresina com foco em produtos frescos e tecnologia de ponta.</p>
            <p>A nova unidade conta com mais de 3000 metros quadrados de área de vendas e gerou 200 novos empregos diretos para a comunidade local da capital piauiense.</p>
          </body>
        </html>
        """
        mock_extrair_html.return_value = {
            "html": html_content,
            "final_url": "https://carvalho.com.br/noticia-1",
            "content_type": "text/html",
        }

        res = extrair_pagina("https://carvalho.com.br/noticia-1", ativo_playwright=False)
        self.assertTrue(res["direta"])
        self.assertEqual(res["titulo"], "Notícia Comercial")
        self.assertIn("Teresina", res["conteudo"])
        self.assertEqual(res["data_publicacao"], "2026-08-20T10:00:00Z")

    @patch("web.extractor.extrair_html")
    @patch("web.extractor.extrair_playwright")
    def test_04_extrair_pagina_fallback_to_playwright(self, mock_pw, mock_html):
        """4. Valida acionamento do fallback Playwright quando o HTML estático é quase vazio (< 250 chars)."""
        mock_html.return_value = {
            "html": "<html><body><div id='app'>Carregando...</div></body></html>",
            "final_url": "https://spa-app.com.br",
            "content_type": "text/html",
        }
        mock_pw.return_value = {
            "titulo": "SPA Carregado",
            "conteudo": "Conteúdo dinâmico completo extraído após hidratação do JavaScript no navegador.",
            "final_url": "https://spa-app.com.br",
            "data_publicacao": "",
        }

        res = extrair_pagina("https://spa-app.com.br", ativo_playwright=True)
        self.assertTrue(res["direta"])
        self.assertEqual(res["titulo"], "SPA Carregado")
        self.assertIn("Conteúdo dinâmico", res["conteudo"])
        mock_pw.assert_called_once_with("https://spa-app.com.br", mgr=None, ativo=True)

    @patch("web.extractor.extrair_pagina")
    def test_05_enriquecer_deterministic_order(self, mock_extrair_pagina):
        """5. Valida enriquecimento concorrente determinístico e preservação das instâncias Fonte."""
        fontes = [
            Fonte(id=1, titulo="Fonte A", url="https://site-a.com", resumo_busca="Resumo A", origem="web", score=90.0),
            Fonte(id=2, titulo="Fonte B", url="https://site-b.com", resumo_busca="Resumo B", origem="web", score=75.0),
            Fonte(id=3, titulo="Fonte C", url="https://site-c.com", resumo_busca="Resumo C", origem="web", score=50.0),
        ]

        def fake_extract(url, mgr=None, session=None):
            return {
                "titulo": f"Título Enriquecido {url}",
                "conteudo": f"Texto longo enriquecido da página {url}",
                "data_publicacao": "2026-08-01",
                "final_url": url,
                "direta": True,
            }

        mock_extrair_pagina.side_effect = fake_extract

        res = enriquecer(
            fontes=fontes,
            max_enriquecimento=2,
            max_workers=2,
            max_fontes_finais=10,
            score_fonte_fn=lambda f: f.score + 5.0,
        )

        # Somente as top 2 devem ter sido enriquecidas
        self.assertEqual(len(res), 3)
        self.assertTrue(res[0].direta)
        self.assertTrue(res[1].direta)
        self.assertFalse(res[2].direta)  # Terceira fonte não foi enviada para o enriquecimento
        self.assertEqual(res[0].id, 1)
        self.assertEqual(res[1].id, 2)
        self.assertEqual(res[2].id, 3)

    def test_06_web_public_api_exports(self):
        """6. Valida exportações formais do pacote web."""
        expected = [
            "PersistentPlaywrightManager",
            "extrair_html",
            "extrair_playwright",
            "extrair_pagina",
            "enriquecer",
        ]
        self.assertEqual(set(web.__all__), set(expected))
        for sym in expected:
            self.assertTrue(hasattr(web, sym), f"Missing symbol {sym} on web package")


if __name__ == "__main__":
    unittest.main()
