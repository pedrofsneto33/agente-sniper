# -*- coding: utf-8 -*-
"""
Testes Unitários do Motor Genérico de Extração Espacial — Fase 2
"""

import unittest
from extractors.models import (
    BoundingBox,
    SpatialToken,
    ExclusionZone,
    RawSpatialDocument,
    CandidateAnchor,
    EvidenceRegion,
    ExtractedEntity,
    EvidenceItem,
    ExtractionResult,
)
from extractors.spatial_normalizer import normalizar_documento_espacial
from extractors.candidates import (
    StrictCurrencyRule,
    MeasurementContextRule,
    CandidateDetector,
)
from extractors.clustering import clusterizar_espacialmente
from extractors.entity_resolver import GenericEntityResolver


class TestExtractionGeneric(unittest.TestCase):
    """Testa a esteira genérica e componentes matemáticos de extração espacial."""

    def test_01_bounding_box_geometria(self):
        """Testa propriedades e métodos geométricos de BoundingBox."""
        box1 = BoundingBox(x_min=10.0, y_min=20.0, x_max=50.0, y_max=80.0)
        self.assertEqual(box1.largura, 40.0)
        self.assertEqual(box1.altura, 60.0)
        self.assertEqual(box1.centro_x, 30.0)
        self.assertEqual(box1.centro_y, 50.0)
        self.assertEqual(box1.area, 2400.0)

        # Inversão de coordenadas automática
        box_inv = BoundingBox(x_min=50.0, y_min=80.0, x_max=10.0, y_max=20.0)
        self.assertEqual(box_inv.x_min, 10.0)
        self.assertEqual(box_inv.x_max, 50.0)

        # Pertinência e interseção
        self.assertTrue(box1.contains_point(30.0, 50.0))
        self.assertFalse(box1.contains_point(5.0, 50.0))

        box2 = BoundingBox(x_min=30.0, y_min=50.0, x_max=70.0, y_max=100.0)
        self.assertTrue(box1.intersects(box2))
        self.assertGreater(box1.iou(box2), 0.0)

        # Expansão
        box_expanded = box1.expand(box2)
        self.assertEqual(box_expanded.x_min, 10.0)
        self.assertEqual(box_expanded.y_min, 20.0)
        self.assertEqual(box_expanded.x_max, 70.0)
        self.assertEqual(box_expanded.y_max, 100.0)

    def test_02_normalizacao_e_zonas_de_exclusao(self):
        """Testa descarte de tokens em zonas de cabeçalho e rodapé."""
        dimensoes = (1000.0, 2000.0)
        t_header = SpatialToken("LOGO CABECALHO", BoundingBox(100, 50, 400, 100), confianca=0.95, id_token=1)
        t_corpo = SpatialToken("PRODUTO CORPO", BoundingBox(100, 500, 400, 550), confianca=0.90, id_token=2)
        t_footer = SpatialToken("DISCLAIMER RODAPE", BoundingBox(100, 1900, 400, 1950), confianca=0.85, id_token=3)
        t_low_conf = SpatialToken("RUIDO", BoundingBox(100, 600, 200, 620), confianca=0.10, id_token=4)

        doc = RawSpatialDocument(
            identificador="doc_teste",
            origem="synthetic",
            dimensoes=dimensoes,
            tokens=[t_header, t_corpo, t_footer, t_low_conf]
        )

        zonas = [
            ExclusionZone("topo", BoundingBox(0.0, 0.0, 1.0, 0.10)),     # 0 a 200px
            ExclusionZone("base", BoundingBox(0.0, 0.90, 1.0, 1.00)),   # 1800 a 2000px
        ]

        doc_norm = normalizar_documento_espacial(doc, zonas_exclusao=zonas, confianca_minima=0.20)
        # Apenas t_corpo deve sobreviver
        self.assertEqual(len(doc_norm.tokens), 1)
        self.assertEqual(doc_norm.tokens[0].texto, "PRODUTO CORPO")

    def test_03_strict_currency_rule_discriminacao(self):
        """Testa diferenciação rigorosa entre preços e gramaturas/dimensões."""
        rule = StrictCurrencyRule()
        doc_dummy = RawSpatialDocument("doc", "dummy", (1000, 1000))

        # Preços válidos
        t_p1 = SpatialToken("17,90", BoundingBox(10, 10, 50, 30), confianca=0.95, id_token=1)
        t_p2 = SpatialToken("R$ 3,29 CADA", BoundingBox(10, 50, 100, 70), confianca=0.98, id_token=2)
        t_p3 = SpatialToken("85,90", BoundingBox(10, 90, 50, 110), confianca=0.90, id_token=3)

        # Falsos positivos comuns (gramaturas e medidas)
        t_fp1 = SpatialToken("162,4g", BoundingBox(10, 150, 50, 170), confianca=0.95, id_token=4)
        t_fp2 = SpatialToken("156,8 g", BoundingBox(10, 190, 60, 210), confianca=0.95, id_token=5)
        t_fp3 = SpatialToken("10x5,2g", BoundingBox(10, 230, 60, 250), confianca=0.95, id_token=6)
        t_fp4 = SpatialToken("15W40", BoundingBox(10, 270, 50, 290), confianca=0.95, id_token=7)
        t_fp5 = SpatialToken("35X35CM", BoundingBox(10, 310, 60, 330), confianca=0.95, id_token=8)
        t_fp6 = SpatialToken("175/70", BoundingBox(10, 350, 60, 370), confianca=0.95, id_token=9)

        tokens = [t_p1, t_p2, t_p3, t_fp1, t_fp2, t_fp3, t_fp4, t_fp5, t_fp6]
        ancoras = rule.detect(tokens, doc_dummy)

        valores_detectados = [a.valor_normalizado for a in ancoras]
        self.assertEqual(len(ancoras), 3)
        self.assertIn(17.90, valores_detectados)
        self.assertIn(3.29, valores_detectados)
        self.assertIn(85.90, valores_detectados)
        self.assertNotIn(162.4, valores_detectados)

    def test_04_measurement_context_rule(self):
        """Testa catalogação de grandezas e especificações."""
        rule = MeasurementContextRule()
        doc_dummy = RawSpatialDocument("doc", "dummy", (1000, 1000))
        t1 = SpatialToken("CAIXETA 10X5,2G", BoundingBox(10, 10, 100, 30), id_token=1)
        t2 = SpatialToken("PACOTE 1KG", BoundingBox(10, 40, 100, 60), id_token=2)
        t3 = SpatialToken("FRASCO 500ML", BoundingBox(10, 70, 100, 90), id_token=3)

        medidas = rule.detect([t1, t2, t3], doc_dummy)
        textos = [m.texto_bruto for m in medidas]
        self.assertTrue(any("10X5,2G" in txt.upper() for txt in textos))
        self.assertTrue(any("1KG" in txt.upper() for txt in textos))
        self.assertTrue(any("500ML" in txt.upper() for txt in textos))

    def test_05_clustering_espacial_delimitado(self):
        """Testa clustering sem expansão infinita e agrupamento correto."""
        dimensoes = (1000.0, 1000.0)
        # Duas âncoras distintas
        t_anc1 = SpatialToken("10,00", BoundingBox(200, 300, 260, 330), id_token=1)
        anc1 = CandidateAnchor("CURRENCY", "10,00", 10.0, "BRL", 0.9, t_anc1, t_anc1.bbox)

        t_anc2 = SpatialToken("20,00", BoundingBox(700, 300, 760, 330), id_token=2)
        anc2 = CandidateAnchor("CURRENCY", "20,00", 20.0, "BRL", 0.9, t_anc2, t_anc2.bbox)

        # Tokens de contexto
        t_ctx1 = SpatialToken("PRODUTO UM", BoundingBox(200, 250, 300, 280), id_token=3)
        t_ctx2 = SpatialToken("PRODUTO DOIS", BoundingBox(700, 250, 800, 280), id_token=4)

        doc = RawSpatialDocument("doc", "synth", dimensoes, [t_anc1, t_anc2, t_ctx1, t_ctx2])
        regioes = clusterizar_espacialmente(doc, [anc1, anc2])

        self.assertEqual(len(regioes), 2)
        # Região 1 deve conter t_ctx1
        c1_textos = [t.texto for t in regioes[0].tokens_incluidos]
        self.assertIn("PRODUTO UM", c1_textos)
        self.assertNotIn("PRODUTO DOIS", c1_textos)

        # Região 2 deve conter t_ctx2
        c2_textos = [t.texto for t in regioes[1].tokens_incluidos]
        self.assertIn("PRODUTO DOIS", c2_textos)
        self.assertNotIn("PRODUTO UM", c2_textos)

    def test_06_tokens_sem_geometria_suporte_sequencial(self):
        """Testa processamento de documento textual sem coordenadas (HTML/TXT)."""
        t1 = SpatialToken("PRODUTO TEXTUAL", bbox=None, id_token=1)
        t2 = SpatialToken("R$ 50,00", bbox=None, id_token=2)
        doc = RawSpatialDocument("doc_txt", "html", (0, 0), [t1, t2])

        doc_norm = normalizar_documento_espacial(doc)
        self.assertEqual(len(doc_norm.tokens), 2)
        self.assertFalse(doc_norm.tokens[0].has_geometry)

        detector = CandidateDetector([StrictCurrencyRule()])
        ancoras = detector.detect_anchors(doc_norm)
        self.assertEqual(len(ancoras), 1)
        self.assertEqual(ancoras[0].valor_normalizado, 50.0)

        regioes = clusterizar_espacialmente(doc_norm, ancoras)
        self.assertEqual(len(regioes), 1)
        self.assertIn("PRODUTO TEXTUAL", [t.texto for t in regioes[0].tokens_incluidos])

    def test_07_origem_multiplas_ancoras_e_sem_ancora(self):
        """Testa entidades originadas por múltiplas âncoras e por apenas contexto."""
        # 1. Região com múltiplas âncoras (ex: atacado vs varejo)
        t_anc1 = SpatialToken("10,00", BoundingBox(10, 10, 50, 30), id_token=1)
        t_anc2 = SpatialToken("8,50", BoundingBox(60, 10, 100, 30), id_token=2)
        anc1 = CandidateAnchor("CURRENCY", "10,00", 10.0, "BRL", 0.9, t_anc1, t_anc1.bbox)
        anc2 = CandidateAnchor("CURRENCY", "8,50", 8.5, "BRL", 0.9, t_anc2, t_anc2.bbox)
        t_ctx = SpatialToken("PRODUTO DUPLO PREÇO", BoundingBox(10, 40, 200, 60), id_token=3)

        reg_multi = EvidenceRegion(
            identificador="reg_multi",
            ancoras=[anc1, anc2],
            tokens_incluidos=[t_ctx]
        )

        resolver = GenericEntityResolver("produto_multivalor")
        ent_multi = resolver.resolve_region(reg_multi)
        self.assertIsNotNone(ent_multi)
        self.assertEqual(ent_multi.origem_tipo, "multiplas_ancoras")
        self.assertEqual(len(ent_multi.valores), 2)

        # 2. Região sem âncoras (apenas contexto descritivo)
        reg_sem_ancora = EvidenceRegion(
            identificador="reg_info",
            ancoras=[],
            tokens_incluidos=[SpatialToken("AVISO INSTITUCIONAL", id_token=4)]
        )
        ent_info = resolver.resolve_region(reg_sem_ancora)
        self.assertIsNotNone(ent_info)
        self.assertEqual(ent_info.origem_tipo, "apenas_contexto")
        self.assertIsNone(ent_info.valor)

    def test_08_cross_card_isolation(self):
        """Testa isolamento estrito entre cards adjacentes para impedir invasão cross-card."""
        dim = (1000.0, 1000.0)
        # Card 1 (Esquerda): x=100..250, y=200..350
        t1 = SpatialToken("SACO 18KG", BoundingBox(100, 200, 220, 230), id_token=1)
        t_anc1 = SpatialToken("99,90", BoundingBox(100, 280, 200, 320), id_token=2)
        anc1 = CandidateAnchor("CURRENCY", "99,90", 99.9, "BRL", 0.9, t_anc1, t_anc1.bbox)

        # Card 2 (Direita): x=350..500, y=200..350
        t2 = SpatialToken("PACOTE 900G", BoundingBox(350, 200, 480, 230), id_token=3)
        t_anc2 = SpatialToken("19,90", BoundingBox(350, 280, 450, 320), id_token=4)
        anc2 = CandidateAnchor("CURRENCY", "19,90", 19.9, "BRL", 0.9, t_anc2, t_anc2.bbox)

        doc = RawSpatialDocument("doc_cross", "test", dim, [t1, t_anc1, t2, t_anc2])
        regioes = clusterizar_espacialmente(doc, [anc1, anc2], max_distancia_horizontal_rel=0.22, max_distancia_vertical_rel=0.40)

        self.assertEqual(len(regioes), 2)
        r1_tokens = [t.texto for t in regioes[0].tokens_incluidos]
        r2_tokens = [t.texto for t in regioes[1].tokens_incluidos]

        # Região 1 deve conter apenas SACO 18KG
        self.assertIn("SACO 18KG", r1_tokens)
        self.assertNotIn("PACOTE 900G", r1_tokens)

        # Região 2 deve conter apenas PACOTE 900G
        self.assertIn("PACOTE 900G", r2_tokens)
        self.assertNotIn("SACO 18KG", r2_tokens)

    def test_09_disclaimer_exclusion(self):
        """Testa descarte estrito de disclaimers jurídicos e preservação de produtos longos."""
        from extractors.adapters.flyer_product_adapter import FlyerProductAdapter
        adapter = FlyerProductAdapter()

        tokens = [
            SpatialToken("COLEIRA PARA CAES SOLA", BoundingBox(100, 200, 300, 230), 0.99, 1),
            SpatialToken("FORRADA M PRIME FULL", BoundingBox(100, 240, 300, 270), 0.99, 2),
            SpatialToken("R$ 15,90", BoundingBox(100, 300, 200, 350), 0.99, 3),
            SpatialToken("PREÇOS VÁLIDOS PARA TODAS AS LOJAS DO PIAUÍ, DE 17 A 21/08/2026 OU ENQUANTO DURAREM OS ESTOQUES", BoundingBox(50, 400, 950, 430), 0.99, 4),
            SpatialToken("IMAGENS MERAMENTE ILUSTRATIVAS", BoundingBox(50, 440, 400, 460), 0.99, 5)
        ]
        doc = RawSpatialDocument("doc_disc", "test", (1000, 1000), tokens)
        res = adapter.processar_documento(doc)

        self.assertEqual(len(res.entidades), 1)
        nome = res.entidades[0].atributos.get("nome", "")
        self.assertIn("COLEIRA PARA CAES SOLA", nome)
        self.assertIn("FORRADA M PRIME FULL", nome)
        self.assertNotIn("PREÇOS VÁLIDOS", nome)
        self.assertNotIn("ILUSTRATIVAS", nome)

    def test_10_commercial_condition_filtering(self):
        """Testa descarte de condições comerciais isoladas e preservação de descrições legítimas."""
        from extractors.adapters.flyer_product_adapter import FlyerProductAdapter
        adapter = FlyerProductAdapter()

        # 1. Caso com condição comercial isolada abaixo do preço (atacado)
        tokens_cond = [
            SpatialToken("SABORES CÃES VITTAMAX", BoundingBox(100, 200, 300, 230), 0.99, 1),
            SpatialToken("R$ 19,90", BoundingBox(100, 250, 200, 300), 0.99, 2),
            SpatialToken("A PARTIR DE 3 UN.", BoundingBox(100, 320, 280, 340), 0.99, 3),
        ]
        doc1 = RawSpatialDocument("doc_c1", "test", (1000, 1000), tokens_cond)
        res1 = adapter.processar_documento(doc1)
        self.assertEqual(len(res1.entidades), 1)
        nome1 = res1.entidades[0].atributos.get("nome", "")
        self.assertIn("VITTAMAX", nome1)
        self.assertNotIn("A PARTIR DE", nome1)
        self.assertEqual(res1.entidades[0].atributos.get("condicao_comercial"), "A PARTIR DE 3 UN.")

        # 2. Casos de NÃO-rejeição: embalagens e kits legítimos com "UN"
        legitimos = ["PACOTE COM 3 UN", "KIT 3 UNIDADES", "CAIXA COM 3 UN", "JOGO 3 UNIDADES", "FARDO 3 UN"]
        for idx, leg_name in enumerate(legitimos):
            toks = [
                SpatialToken(leg_name, BoundingBox(100, 200, 300, 230), 0.99, 1),
                SpatialToken("R$ 10,00", BoundingBox(100, 250, 200, 300), 0.99, 2),
            ]
            doc = RawSpatialDocument(f"doc_leg_{idx}", "test", (1000, 1000), toks)
            res = adapter.processar_documento(doc)
            self.assertEqual(len(res.entidades), 1)
            self.assertIn(leg_name, res.entidades[0].atributos.get("nome", ""))

    def test_11_case1_dual_anchor_resolution(self):
        """Testa resolução do Caso 1: âncora forte (R$ 20,79) domina bare decimal espúrio (162,49)."""
        from extractors.adapters.flyer_product_adapter import FlyerProductAdapter
        adapter = FlyerProductAdapter()

        tokens = [
            SpatialToken("1624 9", BoundingBox(100, 100, 150, 120), 0.92, 1),
            SpatialToken("162,49", BoundingBox(100, 125, 140, 142), 0.97, 2), # Bare decimal espúrio (h=17px)
            SpatialToken("CAPPUCCINO PREMIUM", BoundingBox(100, 150, 350, 180), 0.99, 3),
            SpatialToken("CAIXETA 156,8G OU 162,4G", BoundingBox(100, 190, 350, 215), 0.85, 4),
            SpatialToken("R$", BoundingBox(100, 220, 130, 250), 0.98, 5),
            SpatialToken("20,79", BoundingBox(135, 220, 280, 280), 0.99, 6), # Preço forte com R$ e CADA (h=60px)
            SpatialToken("CADA", BoundingBox(200, 270, 260, 290), 0.95, 7)
        ]
        doc = RawSpatialDocument("doc_case1_sim", "test", (1000, 1000), tokens)
        res = adapter.processar_documento(doc)

        # Deve gerar EXATAMENTE 1 entidade consolidada com o preço real de R$ 20,79
        self.assertEqual(len(res.entidades), 1)
        ent = res.entidades[0]
        self.assertEqual(ent.valor, 20.79)
        self.assertIn("CAPPUCCINO PREMIUM", ent.atributos.get("nome", ""))
        self.assertNotEqual(ent.valor, 162.49)


if __name__ == "__main__":
    unittest.main()



