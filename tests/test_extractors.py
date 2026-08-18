# -*- coding: utf-8 -*-
"""
Testes Unitários de Extração de Produtos, JSON-LD e Matching de Preços — Agente Sniper v11.8.1
Cobre: _extract_product_objects, _walk_json, _extract_price_from_obj, similaridade_produto.
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import agente_sniper_v11_8 as sniper


class TestExtractors(unittest.TestCase):

    def test_01_extract_product_objects_com_json_ld_valido(self):
        """Testa extração de produto estruturado a partir de JSON-LD Schema.org."""
        html_ld = """
        <!DOCTYPE html>
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org/",
                "@type": "Product",
                "name": "Arroz Branco Tio João Tipo 1 1kg",
                "brand": {"@type": "Brand", "name": "Tio João"},
                "sku": "TJ-1001",
                "offers": {
                    "@type": "Offer",
                    "priceCurrency": "BRL",
                    "price": "6.89",
                    "availability": "https://schema.org/InStock"
                }
            }
            </script>
        </head>
        <body>
            <h1>Página de Produto</h1>
        </body>
        </html>
        """
        produtos = sniper._extract_product_objects(
            html=html_ld, source="Carvalho", role="target",
            page_url="https://carvalhosupershop.com.br/produto/arroz"
        )
        self.assertEqual(len(produtos), 1)
        p = produtos[0]
        self.assertEqual(p.source, "Carvalho")
        self.assertEqual(p.role, "target")
        self.assertEqual(p.price, 6.89)
        self.assertEqual(p.brand, "Tio João")
        self.assertEqual(p.sku, "TJ-1001")

    def test_02_extract_product_objects_fallback_html_text(self):
        """Testa extração de produto em páginas HTML simples com contexto comercial."""
        html_puro = """
        <html>
        <body>
            <div class="card-produto">
                <a href="/produto/feijao">Feijão Carioca Camil 1kg</a>
                <span class="preco">R$ 8,49</span>
                <button>Comprar oferta</button>
            </div>
        </body>
        </html>
        """
        produtos = sniper._extract_product_objects(
            html=html_puro, source="Mateus", role="competitor",
            page_url="https://mateus.com.br/ofertas"
        )
        self.assertGreaterEqual(len(produtos), 1)
        p = produtos[0]
        self.assertEqual(p.price, 8.49)
        self.assertIn("feijao", sniper.normalizar(p.name))

    def test_03_extract_product_objects_json_ld_malformado(self):
        """Garante resiliência diante de JSON-LD sintaticamente inválido sem lançar exceção."""
        html_invalido = """
        <html>
        <head>
            <script type="application/ld+json">
                { "name": "Produto Incompleto", "offers": ... JSON_CORROMPIDO ... }
            </script>
        </head>
        <body>Conteudo</body>
        </html>
        """
        # Não deve lançar exceção
        produtos = sniper._extract_product_objects(
            html=html_invalido, source="Assai", role="competitor",
            page_url="https://assai.com.br/invalido"
        )
        self.assertIsInstance(produtos, list)

    def test_04_walk_json_aninhamento_profundo(self):
        """Testa travessia iterativa de estruturas JSON aninhadas."""
        dados = {
            "catalog": {
                "items": [
                    {"@type": "Product", "name": "Item A", "price": 10.0},
                    {"nested": {"@type": "Product", "name": "Item B", "price": 20.0}}
                ]
            }
        }
        objetos = list(sniper._walk_json(dados))
        self.assertGreaterEqual(len(objetos), 3)

    def test_05_extract_price_from_obj_variantes(self):
        """Testa extração de preços em múltiplos formatos de dicionário."""
        self.assertEqual(sniper._extract_price_from_obj({"price": "14.90"}), 14.90)
        self.assertEqual(sniper._extract_price_from_obj({"lowPrice": 9.99}), 9.99)
        self.assertEqual(sniper._extract_price_from_obj({"offers": {"price": "22,50"}}), 22.50)
        self.assertIsNone(sniper._extract_price_from_obj({"sem_campo": 123}))

    def test_06_similaridade_produto_regras_avancadas(self):
        """Testa o cálculo fuzzy de similaridade com equivalência de unidades, marca e SKU."""
        # 1. Equivalência 1kg vs 1000g com mesma marca -> alta similaridade
        p1 = sniper.PriceItem("Carvalho", "target", "Arroz Camil 1kg", "https://a.com", 6.50, brand="Camil", unit="1kg", sku="SKU1")
        p2 = sniper.PriceItem("Mateus", "competitor", "Arroz Branco Camil 1000g", "https://b.com", 6.20, brand="Camil", unit="1000g", sku="SKU1")
        sim_kg_g = sniper.similaridade_produto(p1, p2)
        self.assertGreaterEqual(sim_kg_g, 0.85)

        # 2. Equivalência 1L vs 1000ml -> alta similaridade
        p_oleo1 = sniper.PriceItem("Carvalho", "target", "Óleo de Soja Soya 900ml", "https://a.com", 7.20, brand="Soya", unit="900ml")
        p_oleo2 = sniper.PriceItem("Assai", "competitor", "Óleo Soja Soya 900 ml", "https://b.com", 6.99, brand="Soya", unit="900ml")
        sim_oleo = sniper.similaridade_produto(p_oleo1, p_oleo2)
        self.assertGreaterEqual(sim_oleo, 0.85)

        # 3. Marcas diferentes penalizam a similaridade
        p_marca_dif = sniper.PriceItem("Mateus", "competitor", "Arroz Tio João 1kg", "https://c.com", 7.50, brand="Tio João", unit="1kg")
        sim_marca = sniper.similaridade_produto(p1, p_marca_dif)
        self.assertLess(sim_marca, sim_kg_g)

        # 4. Produtos de categorias totalmente distintas
        p_limpeza = sniper.PriceItem("Atacadao", "competitor", "Detergente Ypê Neutro 500ml", "https://d.com", 2.50, brand="Ypê", unit="500ml")
        sim_distinta = sniper.similaridade_produto(p1, p_limpeza)
        self.assertLess(sim_distinta, 0.35)


if __name__ == "__main__":
    unittest.main()
