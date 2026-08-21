"""
Testes Unitários do Módulo pricing (Fase 42B).
Validação abrangente e isolada de classificação de URLs, JSON-LD, heurística HTML,
descoberta de fontes, coleta OCR/Web e matriz de comparação de preços sem dependência de rede externa.
"""

import unittest
from unittest.mock import MagicMock, patch

from domain.models import Fonte, PriceItem
from pricing import (
    is_price_candidate_url,
    _price_page_type,
    _commercial_signal_url,
    _is_blocked_price_domain,
    _is_non_commercial_url,
    _walk_json,
    _extract_price_from_obj,
    _plausible_price,
    _price_item_confidence,
    _extract_product_objects,
    _extract_commercial_links,
    _expand_commercial_domain,
    descobrir_fontes_preco,
    mesclar_price_sources,
    coletar_itens_preco_fonte,
    comparar_precos,
    carregar_price_sources,
)
import agente_sniper_v11_8 as sniper


class TestPricingModule(unittest.TestCase):

    def test_01_url_classification_and_commercial_signals(self):
        """1. Valida classificação determinística de URLs comerciais, bloqueadas e neutras."""
        # Classificação e sinais de página comercial
        self.assertEqual(_price_page_type("https://carvalho.com.br/ofertas"), "COMMERCIAL_CANDIDATE")
        self.assertEqual(_price_page_type("https://empresa.com.br/"), "ROOT_CANDIDATE")
        self.assertGreater(_commercial_signal_url("https://carvalho.com.br/promocao"), 0.0)

        # Domínio bloqueado (ex: notícias, regulação, tribunais)
        self.assertFalse(is_price_candidate_url("https://www.jusbrasil.com.br/processos/123"))
        self.assertTrue(_is_blocked_price_domain("https://g1.globo.com/economia"))
        self.assertEqual(_price_page_type("https://reclameaqui.com.br/empresa"), "BLOCKED")

        # URL de RH / Trabalhe Conosco (Não comercial)
        self.assertTrue(_is_non_commercial_url("https://empresa.com.br/trabalhe-conosco/vagas"))
        self.assertEqual(_price_page_type("https://empresa.com.br/carreiras"), "ARTICLE_OR_EMPLOYMENT")

    def test_02_json_ld_schema_org_extraction(self):
        """2. Valida extração profunda e estruturada de produtos a partir de JSON-LD Schema.org."""
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org/",
                "@type": "Product",
                "name": "Café Torrado e Moído Pilão 500g",
                "brand": {"@type": "Brand", "name": "Pilão"},
                "sku": "PIL-500G",
                "oldPrice": "21.90",
                "offers": {
                    "@type": "Offer",
                    "priceCurrency": "BRL",
                    "price": "18.90"
                }
            }
            </script>
        </head>
        <body>Página de Produto</body>
        </html>
        """
        items = _extract_product_objects(html, source="Carvalho", role="target", page_url="https://loja.carvalho.com.br/cafe")
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it.name, "Café Torrado e Moído Pilão 500g")
        self.assertEqual(it.brand, "Pilão")
        self.assertEqual(it.price, 18.90)
        self.assertEqual(it.old_price, 21.90)
        self.assertTrue(it.promotion)
        self.assertEqual(it.sku, "PIL-500G")
        self.assertGreaterEqual(it.price_confidence, 0.70)

    def test_03_html_text_fallback_extraction(self):
        """3. Valida extração heurística via DOM de ofertas com regex monetária quando não há JSON-LD."""
        html = """
        <html>
        <body>
            <div class="card-oferta">
                <a href="/produto/leite">Leite Integral Piracanjuba 1L</a>
                <span class="preco-valor">R$ 5,29</span>
                <button>Comprar Agora</button>
            </div>
        </body>
        </html>
        """
        items = _extract_product_objects(html, source="Mateus", role="competitor", page_url="https://mateus.com.br/ofertas")
        self.assertGreaterEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it.price, 5.29)
        self.assertIn("leite", it.name.lower())

    def test_04_plausible_price_filtering(self):
        """4. Valida rejeição estrita de preços implausíveis (salários, PIB, cotações, valores > 1M)."""
        self.assertFalse(_plausible_price("PIB do Brasil cresce", 2.5))
        self.assertFalse(_plausible_price("Vaga de Emprego Salário Mensal", 3500.0, context="salario"))
        self.assertFalse(_plausible_price("Lucro em Milhões", 5000000.0))
        self.assertFalse(_plausible_price("Preço Zero", 0.0))
        self.assertFalse(_plausible_price("Preço Negativo", -10.0))
        self.assertTrue(_plausible_price("Arroz Branco Tipo 1 5kg", 24.90))

    def test_05_commercial_domain_expansion_and_crawling(self):
        """5. Valida extração e ranking de links comerciais dentro de HTML com descarte de links bloqueados."""
        html = """
        <html>
        <body>
            <a href="/produtos/ofertas">Confira Nossas Ofertas e Preços</a>
            <a href="/loja-online/catalogo">Loja Online Catálogo</a>
            <a href="https://jusbrasil.com.br/processo">Jurídico</a>
            <a href="/trabalhe-conosco">Trabalhe Conosco</a>
        </body>
        </html>
        """
        links = _extract_commercial_links("https://supermercadocarvalho.com.br", html, limit=5)
        self.assertTrue(any("ofertas" in u for u in links))
        self.assertTrue(any("catalogo" in u for u in links))
        self.assertFalse(any("jusbrasil" in u for u in links))
        self.assertFalse(any("trabalhe-conosco" in u for u in links))

    def test_06_price_source_discovery_and_merging(self):
        """6. Valida descoberta automática de fontes comerciais e mesclagem idempotente por papel e domínio."""
        fontes = [
            Fonte(id=1, titulo="Supermercado Carvalho - Loja Virtual", url="https://loja.carvalho.com.br/ofertas", origem="web", entidade="Supermercado Carvalho", cidade_confirmada=True),
            Fonte(id=2, titulo="Comercial Carvalho em Teresina", url="https://carvalho.com.br/catalogo", origem="web", entidade="Supermercado Carvalho", cidade_confirmada=True),
            Fonte(id=3, titulo="Notícia Geral de Mercado", url="https://g1.globo.com/noticia", origem="web", entidade="mercado"),
        ]
        with patch.dict("os.environ", {"PRICE_SOURCES_JSON": '[{"name": "Mateus", "role": "competitor", "url": "https://mateus.com.br"}]'}):
            merged = mesclar_price_sources(fontes)
            roles = {s.get("role") for s in merged}
            names = {s.get("name") for s in merged}
            self.assertIn("target", roles)
            self.assertIn("competitor", roles)
            self.assertIn("Supermercado Carvalho", names)
            self.assertIn("Mateus", names)

    def test_07_coletar_itens_preco_fonte_ocr_and_web(self):
        """7. Valida coleta de preços com fallback e integração com extractors.bridge para OCR."""
        # Mock de extração OCR
        with patch("extractors.bridge.executar_pipeline_extracao") as mock_extract:
            mock_extract.return_value = {
                "price_items": [
                    PriceItem("Assai", "competitor", "Café Pilão 500g", "https://assai.com.br", 17.90, unit="500g"),
                    PriceItem("Assai", "competitor", "Leite Ninho 400g", "https://assai.com.br", 14.50, unit="400g"),
                ]
            }
            source_ocr = {"name": "Assai", "role": "competitor", "ocr_path": "dados_browser/ocr_bruto/assai.json"}
            items = coletar_itens_preco_fonte(source_ocr)
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].name, "Café Pilão 500g")
            self.assertEqual(items[0].price, 17.90)

    def test_08_comparar_precos_full_matrix_calculation(self):
        """8. Valida cálculo integral da matriz de comparação de preços e gap percentual com storage mockado."""
        fontes = [
            Fonte(id=1, titulo="Carvalho Loja", url="https://loja.carvalho.com.br", origem="web", entidade="Supermercado Carvalho"),
        ]

        target_items = [
            PriceItem("Supermercado Carvalho", "target", "Arroz Camil 1kg", "https://loja.carvalho.com.br/p1", 6.50, brand="Camil", unit="1kg", price_confidence=0.90),
            PriceItem("Supermercado Carvalho", "target", "Óleo Soya 900ml", "https://loja.carvalho.com.br/p2", 7.20, brand="Soya", unit="900ml", price_confidence=0.90),
        ]
        comp_items = [
            PriceItem("Mateus", "competitor", "Arroz Camil 1000g", "https://mateus.com.br/p1", 6.00, brand="Camil", unit="1000g", price_confidence=0.90),
            PriceItem("Mateus", "competitor", "Óleo Soja Soya 900ml", "https://mateus.com.br/p2", 7.50, brand="Soya", unit="900ml", price_confidence=0.90),
        ]

        def mock_coletar(src, query=""):
            if src.get("role") == "target":
                return target_items
            return comp_items

        with patch("pricing.service.coletar_itens_preco_fonte", side_effect=mock_coletar):
            with patch("pricing.service.carregar_price_sources", return_value=[
                {"name": "Supermercado Carvalho", "role": "target", "url": "https://loja.carvalho.com.br"},
                {"name": "Mateus", "role": "competitor", "url": "https://mateus.com.br"},
            ]):
                res = comparar_precos(fontes, memoria=None)
                self.assertTrue(res.get("enabled"))
                self.assertEqual(res.get("status"), "ok")
                comparacoes = res.get("comparacoes", [])
                self.assertEqual(len(comparacoes), 2)
                # Arroz: Alvo 6.50 vs Concorrente 6.00 -> Concorrente mais barato (-7.69%)
                c1 = [c for c in comparacoes if "Arroz" in c["produto_alvo"]][0]
                self.assertEqual(c1["mais_barato"], "concorrente")
                self.assertLess(c1["dif_percent"], 0)

                # Óleo: Alvo 7.20 vs Concorrente 7.50 -> Alvo mais barato (+4.17%)
                c2 = [c for c in comparacoes if "Óleo" in c["produto_alvo"]][0]
                self.assertEqual(c2["mais_barato"], "alvo")
                self.assertGreater(c2["dif_percent"], 0)

    def test_09_public_contracts_compatibility(self):
        """9. Valida compatibilidade programática entre o monólito e o pacote pricing."""
        symbols = [
            "comparar_precos",
            "coletar_itens_preco_fonte",
            "descobrir_fontes_preco",
            "mesclar_price_sources",
            "is_price_candidate_url",
            "carregar_price_sources",
            "_extract_product_objects",
            "_walk_json",
            "_extract_price_from_obj",
            "_price_page_type",
            "_commercial_signal_url",
            "_is_blocked_price_domain",
            "_is_non_commercial_url",
        ]
        import pricing as pr
        for s in symbols:
            self.assertTrue(hasattr(sniper, s), f"Missing {s} in orchestrator")
            self.assertTrue(hasattr(pr, s), f"Missing {s} in pricing package")
            self.assertTrue(callable(getattr(sniper, s)))
            self.assertTrue(callable(getattr(pr, s)))

    def test_10_niche_commercial_sources_loading(self):
        """10. Valida carregamento automático das fontes comerciais do perfil de nicho na ausência de .env."""
        with patch.dict("os.environ", {"PRECO_ALVO_URLS": "", "PRICE_SOURCES_JSON": ""}, clear=False):
            # Supermercado carrega fontes comerciais auditadas
            sources_super = carregar_price_sources(nicho="supermercado")
            self.assertGreater(len(sources_super), 0)
            names_super = {s["name"] for s in sources_super}
            self.assertIn("Assaí Atacadista", names_super)
            self.assertIn("Pão de Açúcar", names_super)
            # Confirma que Carvalho inválido não está presente
            self.assertNotIn("Carvalho Super", names_super)

            # Farmácia e Genérico mantêm lista vazia no escopo saneado
            self.assertEqual(carregar_price_sources(nicho="farmacia"), [])
            self.assertEqual(carregar_price_sources(nicho="generico"), [])

    def test_11_pricing_precedence_hierarchy(self):
        """11. Valida precedência estrita: PRECO_ALVO_URLS > PRICE_SOURCES_JSON > perfil > vazio."""
        # A. PRECO_ALVO_URLS tem precedência máxima
        with patch.dict("os.environ", {
            "PRECO_ALVO_URLS": "https://custom-target.com/ofertas",
            "PRICE_SOURCES_JSON": '[{"name": "Custom Comp", "role": "competitor", "url": "https://custom-comp.com"}]'
        }):
            srcs = carregar_price_sources(nicho="supermercado")
            self.assertEqual(len(srcs), 1)
            self.assertEqual(srcs[0]["url"], "https://custom-target.com/ofertas")
            self.assertEqual(srcs[0]["role"], "target")

        # B. PRICE_SOURCES_JSON tem precedência sobre o perfil quando PRECO_ALVO_URLS está vazio
        with patch.dict("os.environ", {
            "PRECO_ALVO_URLS": "",
            "PRICE_SOURCES_JSON": '[{"name": "JSON Comp", "role": "competitor", "url": "https://json-comp.com"}]'
        }):
            srcs = carregar_price_sources(nicho="supermercado")
            self.assertEqual(len(srcs), 1)
            self.assertEqual(srcs[0]["name"], "JSON Comp")

        # C. Perfil é usado quando não há variáveis explícitas
        with patch.dict("os.environ", {"PRECO_ALVO_URLS": "", "PRICE_SOURCES_JSON": ""}):
            srcs = carregar_price_sources(nicho="supermercado")
            names = {s["name"] for s in srcs}
            self.assertIn("Assaí Atacadista", names)
            self.assertIn("Pão de Açúcar", names)

    def test_12_channel_type_declarative_safe_degradation(self):
        """12. Valida degradação segura por canal: flyer_ocr e interactive_catalog sem adaptador não inventam preços."""
        # A. flyer_ocr sem payload OCR retorna lista vazia sem tentar crawler HTML
        src_flyer = {"name": "Assaí", "role": "competitor", "url": "https://assai.com.br/ofertas", "channel_type": "flyer_ocr"}
        items_flyer = coletar_itens_preco_fonte(src_flyer)
        self.assertEqual(items_flyer, [])

        # B. interactive_catalog sem adaptador retorna lista vazia
        src_inter = {"name": "Pão de Açúcar", "role": "competitor", "url": "https://paodeacucar.com", "channel_type": "interactive_catalog"}
        items_inter = coletar_itens_preco_fonte(src_inter)
        self.assertEqual(items_inter, [])

        # C. html_catalog com HTML fornecido extrai produtos
        html = """<html><head><script type="application/ld+json">
        {"@context":"https://schema.org/","@type":"Product","name":"Feijão Carioca 1kg","offers":{"@type":"Offer","price":"7.99"}}
        </script></head><body>Loja</body></html>"""
        with patch("pricing.service._price_page_html", return_value=(html, "https://loja.com/feijao")):
            src_html = {"name": "Loja Web", "role": "competitor", "url": "https://loja.com/feijao", "channel_type": "html_catalog"}
            items_html = coletar_itens_preco_fonte(src_html)
            self.assertEqual(len(items_html), 1)
            self.assertEqual(items_html[0].name, "Feijão Carioca 1kg")
            self.assertEqual(items_html[0].price, 7.99)


if __name__ == "__main__":
    unittest.main()
