# -*- coding: utf-8 -*-
"""
Bateria de Testes de Generalização do Motor de Extração — Fase 3
Validação em domínios heterogêneos: Jurídico, Financeiro, Empregos, Tabelas, Texto Puro e Invariância de Escala.
"""

import unittest
from extractors.models import (
    BoundingBox,
    SpatialToken,
    RawSpatialDocument,
    CandidateAnchor,
    EvidenceRegion,
    ExtractedEntity,
    AnchorEvidenceKind,
)
from extractors.spatial_normalizer import normalizar_documento_espacial
from extractors.candidates import (
    StrictCurrencyRule,
    LegalProcessRule,
    PercentageRule,
    SalaryRule,
    TaxIdRule,
    DateRule,
    MeasurementContextRule,
    CandidateDetector,
)
from extractors.clustering import clusterizar_espacialmente
from extractors.entity_resolver import GenericEntityResolver
from extractors.evaluation import GroundTruthItem, avaliar_extracao


class TestGeneralization(unittest.TestCase):
    """Testa a capacidade do motor de operar de forma agnóstica em múltiplos domínios."""

    def test_01_dominio_juridico_processos(self):
        """Testa extração em diário oficial jurídico com número de processo e sanção."""
        dim = (1000.0, 1500.0)
        # Processo 1
        t_proc1 = SpatialToken("Proc. 0812345-67.2026.8.18.0001", BoundingBox(100, 200, 450, 230), id_token=1)
        t_vara1 = SpatialToken("2ª VARA CÍVEL DE TERESINA", BoundingBox(100, 240, 400, 265), id_token=2)
        t_reu1 = SpatialToken("RÉU: EMPRESA DISTRIBUIDORA LTDA", BoundingBox(100, 275, 450, 300), id_token=3)

        # Processo 2
        t_proc2 = SpatialToken("Proc. 0009876-54.2025.8.18.0000", BoundingBox(100, 600, 450, 630), id_token=4)
        t_vara2 = SpatialToken("VARA DE EXECUÇÕES FISCAIS", BoundingBox(100, 640, 400, 665), id_token=5)
        t_reu2 = SpatialToken("RÉU: COMERCIAL SILVA ME", BoundingBox(100, 675, 400, 700), id_token=6)

        doc = RawSpatialDocument("doc_juridico", "legal_gazette", dim, [t_proc1, t_vara1, t_reu1, t_proc2, t_vara2, t_reu2])

        detector = CandidateDetector(rules=[LegalProcessRule()])
        doc_norm = normalizar_documento_espacial(doc)
        ancoras = detector.detect_anchors(doc_norm)

        self.assertEqual(len(ancoras), 2)
        self.assertEqual(ancoras[0].valor_normalizado, "0812345-67.2026.8.18.0001")
        self.assertEqual(ancoras[1].valor_normalizado, "0009876-54.2025.8.18.0000")

        regioes = clusterizar_espacialmente(doc_norm, ancoras)
        resolver = GenericEntityResolver("processo_judicial")
        resultado = resolver.resolve_all(regioes)

        gt = [
            GroundTruthItem("processo_judicial", "0812345-67.2026.8.18.0001", identificador_item="gt_p1"),
            GroundTruthItem("processo_judicial", "0009876-54.2025.8.18.0000", identificador_item="gt_p2"),
        ]
        metricas = avaliar_extracao(resultado.entidades, gt)
        self.assertEqual(metricas.f1_score, 1.0)
        self.assertEqual(metricas.falsos_positivos, 0)

    def test_02_dominio_financeiro_indicadores_e_deltas(self):
        """Testa extração em relatório financeiro (DRE/EBITDA/Percentuais)."""
        dim = (1000.0, 1000.0)
        t_ebitda_label = SpatialToken("EBITDA AJUSTADO", BoundingBox(100, 100, 300, 130), id_token=1)
        t_ebitda_pct = SpatialToken("+18,5%", BoundingBox(350, 100, 450, 130), id_token=2)
        t_rec_label = SpatialToken("RECEITA LIQUIDA", BoundingBox(100, 200, 300, 230), id_token=3)
        t_rec_pct = SpatialToken("-4,2%", BoundingBox(350, 200, 450, 230), id_token=4)

        doc = RawSpatialDocument("doc_fin", "earnings_report", dim, [t_ebitda_label, t_ebitda_pct, t_rec_label, t_rec_pct])

        detector = CandidateDetector(rules=[PercentageRule()])
        doc_norm = normalizar_documento_espacial(doc)
        ancoras = detector.detect_anchors(doc_norm)

        self.assertEqual(len(ancoras), 2)
        self.assertEqual(ancoras[0].valor_normalizado, 18.5)
        self.assertEqual(ancoras[1].valor_normalizado, -4.2)

        regioes = clusterizar_espacialmente(doc_norm, ancoras)
        resolver = GenericEntityResolver("indicador_financeiro")
        resultado = resolver.resolve_all(regioes)

        gt = [
            GroundTruthItem("indicador_financeiro", 18.5, identificador_item="gt_ebitda"),
            GroundTruthItem("indicador_financeiro", -4.2, identificador_item="gt_rec"),
        ]
        metricas = avaliar_extracao(resultado.entidades, gt)
        self.assertEqual(metricas.f1_score, 1.0)

    def test_03_dominio_vagas_emprego(self):
        """Testa extração em anúncio de vagas com salários."""
        dim = (1000.0, 1200.0)
        t_cargo1 = SpatialToken("ENGENHEIRO DE SOFTWARE SENIOR", BoundingBox(100, 150, 500, 180), id_token=1)
        t_sal1 = SpatialToken("SALÁRIO: R$ 15.000,00 / MÊS", BoundingBox(100, 190, 400, 220), id_token=2)

        t_cargo2 = SpatialToken("ANALISTA DE QA JUNIOR", BoundingBox(100, 500, 400, 530), id_token=3)
        t_sal2 = SpatialToken("REMUNERAÇÃO: R$ 4.200,00 CLT", BoundingBox(100, 540, 400, 570), id_token=4)

        doc = RawSpatialDocument("doc_vagas", "job_board", dim, [t_cargo1, t_sal1, t_cargo2, t_sal2])

        detector = CandidateDetector(rules=[SalaryRule()])
        doc_norm = normalizar_documento_espacial(doc)
        ancoras = detector.detect_anchors(doc_norm)

        self.assertEqual(len(ancoras), 2)
        self.assertEqual(ancoras[0].valor_normalizado, 15000.0)
        self.assertEqual(ancoras[1].valor_normalizado, 4200.0)

    def test_04_invariancia_geometrica_de_escala(self):
        """Testa se documentos em resoluções 1000x2000, 2000x4000 e 4000x8000 produzem o mesmo resultado."""
        def criar_doc(escala: float, dim: tuple[float, float]) -> RawSpatialDocument:
            t1 = SpatialToken("PRODUTO TESTE", BoundingBox(100*escala, 400*escala, 400*escala, 450*escala), id_token=1)
            t2 = SpatialToken("R$ 29,90 CADA", BoundingBox(100*escala, 500*escala, 300*escala, 550*escala), id_token=2)
            return RawSpatialDocument(f"doc_scale_{escala}", "synthetic", dim, [t1, t2])

        doc_1k = criar_doc(1.0, (1000.0, 2000.0))
        doc_2k = criar_doc(2.0, (2000.0, 4000.0))
        doc_4k = criar_doc(4.0, (4000.0, 8000.0))

        detector = CandidateDetector([StrictCurrencyRule()])
        resolver = GenericEntityResolver("produto")

        res_1k = resolver.resolve_all(clusterizar_espacialmente(normalizar_documento_espacial(doc_1k), detector.detect_anchors(doc_1k)))
        res_2k = resolver.resolve_all(clusterizar_espacialmente(normalizar_documento_espacial(doc_2k), detector.detect_anchors(doc_2k)))
        res_4k = resolver.resolve_all(clusterizar_espacialmente(normalizar_documento_espacial(doc_4k), detector.detect_anchors(doc_4k)))

        # Os valores e os textos devem ser 100% idênticos
        self.assertEqual(res_1k.entidades[0].valor, 29.90)
        self.assertEqual(res_2k.entidades[0].valor, 29.90)
        self.assertEqual(res_4k.entidades[0].valor, 29.90)
        self.assertEqual(res_1k.entidades[0].atributos["texto_completo"], res_4k.entidades[0].atributos["texto_completo"])

    def test_05_resistencia_extrema_a_falsos_positivos(self):
        """
        Garante discriminação cirúrgica quando 9 formatos conflitantes coexistem no mesmo documento:
        '250g', '1kg', '500ml', '10x5,2g', '17/08/2026', '0812345-67.2026', '00.000.000/0001-00', '15,5%', 'R$ 17,90'.
        """
        dim = (1000.0, 1000.0)
        tokens = [
            SpatialToken("PACOTE 250g", BoundingBox(10, 10, 100, 30), id_token=1),
            SpatialToken("FARINHA 1kg", BoundingBox(10, 40, 100, 60), id_token=2),
            SpatialToken("LEITE 500ml", BoundingBox(10, 70, 100, 90), id_token=3),
            SpatialToken("CAIXA 10x5,2g", BoundingBox(10, 100, 100, 120), id_token=4),
            SpatialToken("VALIDADE 17/08/2026", BoundingBox(10, 130, 150, 150), id_token=5),
            SpatialToken("AUTOS 0812345-67.2026", BoundingBox(10, 160, 200, 180), id_token=6),
            SpatialToken("CNPJ 00.000.000/0001-00", BoundingBox(10, 190, 200, 210), id_token=7),
            SpatialToken("JUROS +15,5%", BoundingBox(10, 220, 100, 240), id_token=8),
            SpatialToken("PREÇO R$ 17,90", BoundingBox(10, 250, 120, 270), id_token=9),
        ]
        doc = RawSpatialDocument("doc_stress", "stress_test", dim, tokens)
        doc_norm = normalizar_documento_espacial(doc)

        # 1. Teste sob regra monetária: APENAS 17.90 deve ser âncora
        ancoras_moeda = CandidateDetector([StrictCurrencyRule()]).detect_anchors(doc_norm)
        self.assertEqual(len(ancoras_moeda), 1)
        self.assertEqual(ancoras_moeda[0].valor_normalizado, 17.90)

        # 2. Teste sob regra de processo judicial: APENAS 0812345-67.2026 deve ser âncora
        ancoras_proc = CandidateDetector([LegalProcessRule()]).detect_anchors(doc_norm)
        self.assertEqual(len(ancoras_proc), 1)
        self.assertEqual(ancoras_proc[0].valor_normalizado, "0812345-67.2026")

        # 3. Teste sob regra de percentual: APENAS 15.5 deve ser âncora
        ancoras_pct = CandidateDetector([PercentageRule()]).detect_anchors(doc_norm)
        self.assertEqual(len(ancoras_pct), 1)
        self.assertEqual(ancoras_pct[0].valor_normalizado, 15.5)

        # 4. Teste sob regra de CNPJ: APENAS o CNPJ deve ser âncora
        ancoras_cnpj = CandidateDetector([TaxIdRule()]).detect_anchors(doc_norm)
        self.assertEqual(len(ancoras_cnpj), 1)
        self.assertEqual(ancoras_cnpj[0].valor_normalizado, "00.000.000/0001-00")

        # 5. Teste sob regra de data: APENAS a data deve ser âncora
        ancoras_data = CandidateDetector([DateRule()]).detect_anchors(doc_norm)
        self.assertEqual(len(ancoras_data), 1)
        self.assertEqual(ancoras_data[0].valor_normalizado, "17/08/2026")

    def test_06_rastreabilidade_forense_total(self):
        """Valida que toda entidade responde: quem originou, quem foi rejeitado, qual regra e por qual motivo."""
        dim = (1000.0, 1000.0)
        t_anc = SpatialToken("R$ 49,90", BoundingBox(100, 300, 200, 330), confianca=0.98, id_token=1)
        t_ctx_perto = SpatialToken("PRODUTO EM OFERTA", BoundingBox(100, 250, 300, 280), confianca=0.92, id_token=2)
        # Token muito longe à direita (excederá max_dx_rel=0.38 -> 380px)
        t_ctx_longe = SpatialToken("OUTRA SEÇÃO DISTANTE", BoundingBox(800, 300, 950, 330), confianca=0.85, id_token=3)

        doc = RawSpatialDocument("doc_audit", "audit_test", dim, [t_anc, t_ctx_perto, t_ctx_longe])
        detector = CandidateDetector([StrictCurrencyRule()])
        doc_norm = normalizar_documento_espacial(doc)
        ancoras = detector.detect_anchors(doc_norm)

        regioes = clusterizar_espacialmente(doc_norm, ancoras)
        self.assertEqual(len(regioes), 1)

        reg = regioes[0]
        # 1. Qual regra criou a âncora?
        self.assertEqual(reg.ancora.metadados["regra_origem"], "StrictCurrencyRule")

        # 2. Quais tokens foram incluídos?
        tokens_inc_ids = [t.id_token for t in reg.tokens_incluidos]
        self.assertIn(2, tokens_inc_ids)

        # 3. Quais tokens foram rejeitados e por quê?
        self.assertEqual(len(reg.tokens_rejeitados), 1)
        self.assertEqual(reg.tokens_rejeitados[0]["token_id"], 3)
        self.assertIn("distancia_excessiva", reg.tokens_rejeitados[0]["motivo"])

        # 4. A entidade final preserva todas as evidências com coordenadas?
        # 4. A entidade final preserva todas as evidências com coordenadas?
        resolver = GenericEntityResolver("produto")
        entidade = resolver.resolve_region(reg)
        self.assertIsNotNone(entidade)
        self.assertEqual(len(entidade.evidencias), 2)
        self.assertIsNotNone(entidade.evidencias[0].bbox)

    def test_09_multiniche_restaurant_bare_price(self):
        """Testa preservação de preço bare-number em restaurante sem símbolo monetário."""
        dim = (1000.0, 1000.0)
        tokens = [
            SpatialToken("PRATO EXECUTIVO FILÉ", BoundingBox(100, 100, 400, 130), id_token=1),
            SpatialToken("59,90", BoundingBox(100, 140, 200, 170), id_token=2),
        ]
        doc = RawSpatialDocument("doc_restaurante", "cardapio", dim, tokens)
        detector = CandidateDetector([StrictCurrencyRule()])
        ancoras = detector.detect_anchors(doc)
        self.assertEqual(len(ancoras), 1)
        self.assertEqual(ancoras[0].valor_normalizado, 59.90)
        self.assertEqual(ancoras[0].evidence_kind, AnchorEvidenceKind.BARE_DECIMAL)

        regioes = clusterizar_espacialmente(doc, ancoras)
        resolver = GenericEntityResolver("item_cardapio")
        res = resolver.resolve_all(regioes)
        self.assertEqual(len(res.entidades), 1)
        self.assertEqual(res.entidades[0].valor, 59.90)

    def test_10_multiniche_clinic_sessions_and_price(self):
        """Testa clínica médica com especificação de sessões e preço explícito."""
        dim = (1000.0, 1000.0)
        tokens = [
            SpatialToken("TRATAMENTO FISIOTERAPIA", BoundingBox(100, 100, 450, 130), id_token=1),
            SpatialToken("10 SESSÕES", BoundingBox(100, 140, 250, 170), id_token=2),
            SpatialToken("R$ 180,00", BoundingBox(100, 180, 250, 210), id_token=3),
        ]
        doc = RawSpatialDocument("doc_clinica", "tabela_precos", dim, tokens)
        detector = CandidateDetector([StrictCurrencyRule()])
        ancoras = detector.detect_anchors(doc)
        self.assertEqual(len(ancoras), 1)
        self.assertEqual(ancoras[0].valor_normalizado, 180.0)
        self.assertEqual(ancoras[0].evidence_kind, AnchorEvidenceKind.EXPLICIT_CURRENCY)

        regioes = clusterizar_espacialmente(doc, ancoras)
        resolver = GenericEntityResolver("procedimento_clinico")
        res = resolver.resolve_all(regioes)
        self.assertEqual(len(res.entidades), 1)
        self.assertEqual(res.entidades[0].valor, 180.0)

    def test_11_multiniche_hotel_daily_package(self):
        """Testa hotelaria com diárias e preço explícito."""
        dim = (1000.0, 1000.0)
        tokens = [
            SpatialToken("SUÍTE LUXO CASAL", BoundingBox(100, 100, 350, 130), id_token=1),
            SpatialToken("2 DIÁRIAS", BoundingBox(100, 140, 220, 170), id_token=2),
            SpatialToken("R$ 350,00", BoundingBox(100, 180, 240, 210), id_token=3),
        ]
        doc = RawSpatialDocument("doc_hotel", "tarifario", dim, tokens)
        detector = CandidateDetector([StrictCurrencyRule()])
        ancoras = detector.detect_anchors(doc)
        self.assertEqual(len(ancoras), 1)
        self.assertEqual(ancoras[0].valor_normalizado, 350.0)

    def test_12_multiniche_saas_monthly_cadence(self):
        """Testa SaaS com planos recorrentes e cadência mensal."""
        dim = (1000.0, 1000.0)
        tokens = [
            SpatialToken("PLANO ENTERPRISE", BoundingBox(100, 100, 350, 130), id_token=1),
            SpatialToken("ATÉ 10 USUÁRIOS", BoundingBox(100, 140, 300, 170), id_token=2),
            SpatialToken("99,90/MÊS", BoundingBox(100, 180, 250, 210), id_token=3),
        ]
        doc = RawSpatialDocument("doc_saas", "pricing_page", dim, tokens)
        detector = CandidateDetector([StrictCurrencyRule()])
        ancoras = detector.detect_anchors(doc)
        self.assertEqual(len(ancoras), 1)
        self.assertEqual(ancoras[0].valor_normalizado, 99.90)
        self.assertEqual(ancoras[0].evidence_kind, AnchorEvidenceKind.CADENCE_PRICE)

    def test_13_multiniche_numeric_coincidence_preservation(self):
        """Testa proteção anti-falso-negativo: número de especificação numericamente igual ao preço."""
        dim = (1000.0, 1000.0)
        tokens = [
            SpatialToken("PACOTE FISIOTERAPIA", BoundingBox(100, 100, 350, 130), id_token=1),
            SpatialToken("10 SESSÕES", BoundingBox(100, 140, 250, 170), id_token=2),
            SpatialToken("10,00", BoundingBox(100, 180, 200, 210), id_token=3),
        ]
        doc = RawSpatialDocument("doc_coincidencia", "tabela", dim, tokens)
        detector = CandidateDetector([StrictCurrencyRule()])
        ancoras = detector.detect_anchors(doc)
        self.assertEqual(len(ancoras), 1)
        self.assertEqual(ancoras[0].valor_normalizado, 10.0)
        # O preço de 10.00 DEVE ser preservado pois é a única âncora econômica da oferta
        regioes = clusterizar_espacialmente(doc, ancoras)
        resolver = GenericEntityResolver("oferta")
        res = resolver.resolve_all(regioes)
        self.assertEqual(len(res.entidades), 1)
        self.assertEqual(res.entidades[0].valor, 10.0)

    def test_14_multiniche_b2b_year_and_price(self):
        """Testa serviços B2B com ano fiscal e valor de contrato."""
        dim = (1000.0, 1000.0)
        tokens = [
            SpatialToken("PROPOSTA COMERCIAL 2026", BoundingBox(100, 100, 450, 130), id_token=1),
            SpatialToken("R$ 5.000,00", BoundingBox(100, 180, 250, 210), id_token=2),
        ]
        doc = RawSpatialDocument("doc_b2b", "proposta", dim, tokens)
        detector = CandidateDetector([StrictCurrencyRule()])
        ancoras = detector.detect_anchors(doc)
        # Apenas 5.000,00 vira âncora; o ano 2026 não vira preço
        self.assertEqual(len(ancoras), 1)
        self.assertEqual(ancoras[0].valor_normalizado, 5000.0)

    def test_15_multiniche_spaced_cadences(self):
        """Testa suporte completo a cadências com variações de espaçamento tipográfico."""
        dim = (1000.0, 1000.0)
        casos_cadencia = [
            ("99,90/mês", AnchorEvidenceKind.CADENCE_PRICE, "/mês"),
            ("99,90 /mês", AnchorEvidenceKind.CADENCE_PRICE, "/mês"),
            ("99,90/ mês", AnchorEvidenceKind.CADENCE_PRICE, "/ mês"),
            ("99,90 / mês", AnchorEvidenceKind.CADENCE_PRICE, "/ mês"),
            ("99,90/ano", AnchorEvidenceKind.CADENCE_PRICE, "/ano"),
            ("99,90 / ano", AnchorEvidenceKind.CADENCE_PRICE, "/ ano"),
            ("R$ 99,90 / mês", AnchorEvidenceKind.EXPLICIT_CURRENCY, "/ mês"),
            ("R$ 99,90 / ano", AnchorEvidenceKind.EXPLICIT_CURRENCY, "/ ano"),
        ]
        rule = StrictCurrencyRule()
        for texto_entrada, kind_esperado, cadencia_esperada in casos_cadencia:
            with self.subTest(texto=texto_entrada):
                tok = SpatialToken(texto_entrada, BoundingBox(100, 100, 250, 130), id_token=1)
                doc = RawSpatialDocument("doc_cad", "teste", dim, [tok])
                ancoras = rule.detect([tok], doc)
                self.assertEqual(len(ancoras), 1, f"Falha ao detectar âncora para '{texto_entrada}'")
                a = ancoras[0]
                self.assertEqual(a.tipo, "CURRENCY")
                self.assertEqual(a.valor_normalizado, 99.90)
                self.assertEqual(a.evidence_kind, kind_esperado)
                self.assertTrue(a.is_strong_monetary_evidence)
                self.assertIsNotNone(a.cadencia)
                self.assertEqual(a.cadencia.lower().replace(" ", ""), cadencia_esperada.lower().replace(" ", ""))

    def test_16_secondary_rules_explicit_evidence_kind(self):
        """Testa a tipagem semântica explícita de evidence_kind nas regras secundárias."""
        dim = (1000.0, 1000.0)
        doc = RawSpatialDocument("doc_sec", "teste", dim, [])

        # 1. LegalProcessRule -> TEMPORAL_OR_CODE
        t_proc = SpatialToken("0812345-67.2026.8.18.0001", BoundingBox(100, 100, 300, 130), id_token=1)
        a_proc = LegalProcessRule().detect([t_proc], doc)
        self.assertEqual(len(a_proc), 1)
        self.assertEqual(a_proc[0].tipo, "LEGAL_PROCESS")
        self.assertEqual(a_proc[0].evidence_kind, AnchorEvidenceKind.TEMPORAL_OR_CODE)

        # 2. DateRule -> TEMPORAL_OR_CODE
        t_date = SpatialToken("19/08/2026", BoundingBox(100, 100, 200, 130), id_token=2)
        a_date = DateRule().detect([t_date], doc)
        self.assertEqual(len(a_date), 1)
        self.assertEqual(a_date[0].tipo, "DATE")
        self.assertEqual(a_date[0].evidence_kind, AnchorEvidenceKind.TEMPORAL_OR_CODE)

        # 3. TaxIdRule (CNPJ & CPF) -> TEMPORAL_OR_CODE
        t_cnpj = SpatialToken("12.345.678/0001-90", BoundingBox(100, 100, 250, 130), id_token=3)
        t_cpf = SpatialToken("123.456.789-00", BoundingBox(100, 100, 200, 130), id_token=4)
        a_cnpj = TaxIdRule().detect([t_cnpj], doc)
        a_cpf = TaxIdRule().detect([t_cpf], doc)
        self.assertEqual(len(a_cnpj), 1)
        self.assertEqual(a_cnpj[0].evidence_kind, AnchorEvidenceKind.TEMPORAL_OR_CODE)
        self.assertEqual(len(a_cpf), 1)
        self.assertEqual(a_cpf[0].evidence_kind, AnchorEvidenceKind.TEMPORAL_OR_CODE)

        # 4. MeasurementContextRule -> SPECIFICATION
        t_meas = SpatialToken("162,4g", BoundingBox(100, 100, 150, 130), id_token=5)
        a_meas = MeasurementContextRule().detect([t_meas], doc)
        self.assertEqual(len(a_meas), 1)
        self.assertEqual(a_meas[0].tipo, "MEASUREMENT")
        self.assertEqual(a_meas[0].evidence_kind, AnchorEvidenceKind.SPECIFICATION)

        # 5. PercentageRule -> BARE_DECIMAL (inalterado nesta etapa)
        t_pct = SpatialToken("15,5%", BoundingBox(100, 100, 150, 130), id_token=6)
        a_pct = PercentageRule().detect([t_pct], doc)
        self.assertEqual(len(a_pct), 1)
        self.assertEqual(a_pct[0].tipo, "PERCENTAGE")
        self.assertEqual(a_pct[0].evidence_kind, AnchorEvidenceKind.BARE_DECIMAL)

    def test_17_scale_invariance_0_5x_to_4x(self):
        """Valida formalmente a invariância de escala geométrica (0.5x, 1.0x, 2.0x, 4.0x) nos 10 documentos reais."""
        from pathlib import Path
        from extractors.adapters.flyer_product_adapter import FlyerProductAdapter
        from extractors.bridge import carregar_ocr_bruto

        ocr_dir = Path("dados_browser/ocr_bruto")
        ocr_files = sorted(list(ocr_dir.glob("*.json")))
        self.assertEqual(len(ocr_files), 10, "Devem existir exatamente 10 arquivos OCR de teste real.")

        adapter = FlyerProductAdapter()
        escalas = [0.5, 1.0, 2.0, 4.0]
        resultados_por_escala = {}

        for escala in escalas:
            total_itens_escala = 0
            produtos_escala = []

            for arq in ocr_files:
                doc_original = carregar_ocr_bruto(arq)
                w_orig, h_orig = doc_original.dimensoes

                if escala == 1.0:
                    doc_escalado = doc_original
                else:
                    tokens_escalados = [
                        SpatialToken(
                            t.texto,
                            BoundingBox(
                                t.bbox.x_min * escala,
                                t.bbox.y_min * escala,
                                t.bbox.x_max * escala,
                                t.bbox.y_max * escala,
                            ) if t.bbox else None,
                            t.confianca,
                            t.id_token,
                            t.metadados
                        )
                        for t in doc_original.tokens
                    ]
                    doc_escalado = RawSpatialDocument(
                        identificador=doc_original.identificador,
                        origem=doc_original.origem,
                        dimensoes=(w_orig * escala, h_orig * escala),
                        tokens=tokens_escalados,
                        metadados=doc_original.metadados
                    )

                resultado = adapter.processar_documento(doc_escalado)
                total_itens_escala += len(resultado.entidades)
                for ent in resultado.entidades:
                    produtos_escala.append((
                        doc_original.identificador,
                        ent.atributos.get("nome"),
                        ent.valor
                    ))

            self.assertEqual(
                total_itens_escala,
                63,
                f"Escala {escala}x produziu {total_itens_escala} itens em vez dos 63 canônicos."
            )
            resultados_por_escala[escala] = produtos_escala

        # Valida invariância semântica e de conteúdo entre 1.0x e todas as demais escalas
        base_1x = resultados_por_escala[1.0]
        for escala in [0.5, 2.0, 4.0]:
            self.assertEqual(
                len(resultados_por_escala[escala]),
                len(base_1x),
                f"Quantidade divergente na escala {escala}x"
            )
            for idx, (p_esc, p_base) in enumerate(zip(resultados_por_escala[escala], base_1x)):
                self.assertEqual(
                    p_esc[0], p_base[0],
                    f"Documento divergente no item {idx} na escala {escala}x"
                )
                self.assertEqual(
                    p_esc[1], p_base[1],
                    f"Nome de produto divergente no item {idx} na escala {escala}x: '{p_esc[1]}' != '{p_base[1]}'"
                )
                self.assertEqual(
                    p_esc[2], p_base[2],
                    f"Valor divergente no item {idx} na escala {escala}x: {p_esc[2]} != {p_base[2]}"
                )

    def test_18_case1_dual_anchor_resolution(self):
        """Testa diretamente o Caso 1: falsa âncora 162,49 gerada de 162,4g subordinada à âncora real R$ 20,79 CADA."""
        from extractors.adapters.flyer_product_adapter import FlyerProductAdapter

        dim = (2000.0, 3000.0)
        tokens = [
            SpatialToken("162,49", BoundingBox(1931.0, 1840.0, 1973.0, 1857.0), id_token=1),
            SpatialToken("CAPPUCCINO PREMIUM", BoundingBox(1794.0, 1875.0, 2077.0, 1904.0), id_token=2),
            SpatialToken("CAIXETA 156,8G OU 162,4G", BoundingBox(1794.0, 1930.0, 2047.0, 1956.0), id_token=3),
            SpatialToken("R$ 20,79 CADA", BoundingBox(1829.0, 1952.0, 2014.0, 2026.0), id_token=4),
        ]
        doc = RawSpatialDocument("doc_caso1", "flyer", dim, tokens)
        adapter = FlyerProductAdapter()
        resultado = adapter.processar_documento(doc)

        self.assertEqual(len(resultado.entidades), 1, "Deveria haver exatamente 1 entidade consolidada (oferta dominante).")
        ent = resultado.entidades[0]
        self.assertEqual(ent.valor, 20.79, "O valor final da oferta deve ser 20.79 (âncora forte dominante).")
        self.assertIn("CAPPUCCINO PREMIUM", ent.atributos.get("nome", "").upper())
        self.assertEqual(len(ent.ancoras), 1, "A entidade dominante possui a âncora principal ativa.")
        self.assertEqual(ent.ancoras[0].valor_normalizado, 20.79)
        self.assertTrue(len(ent.evidencias) >= 2, "A entidade dominante deve incorporar as evidências da região subordinada.")

    def test_19_matching_quantity_and_volume_adversarial(self):
        """Testa o algoritmo de matching com quantização canônica, bônus de equivalência e penalização por volumes distintos."""
        from domain.models import PriceItem
        from domain.matching import similaridade_produto

        # 1. Quantidades diferentes não podem casar (ex: 500g vs 250g)
        p_500g = PriceItem(source="s1", role="r", name="CAFÉ PILÃO 500G", url="u1")
        p_250g = PriceItem(source="s2", role="r", name="CAFÉ PILÃO 250G", url="u2")
        sim_cafe_diff = similaridade_produto(p_500g, p_250g)
        self.assertLess(sim_cafe_diff, 0.45, f"500g vs 250g deve sofrer penalidade estrita: {sim_cafe_diff}")

        # 2. Quantidades equivalentes em unidades distintas devem casar com alta similaridade (500g vs 0.5kg)
        p_05kg = PriceItem(source="s2", role="r", name="CAFÉ PILÃO 0,5KG", url="u2")
        sim_cafe_eq = similaridade_produto(p_500g, p_05kg)
        self.assertGreaterEqual(sim_cafe_eq, 0.90, f"500g vs 0.5kg deve ter alta similaridade: {sim_cafe_eq}")

        # 3. Volumes distintos não podem casar (500ml vs 1L)
        p_500ml = PriceItem(source="s1", role="r", name="ÁGUA MINERAL CRISTAL 500ML", url="u1")
        p_1l = PriceItem(source="s2", role="r", name="ÁGUA MINERAL CRISTAL 1L", url="u2")
        sim_agua_diff = similaridade_produto(p_500ml, p_1l)
        self.assertLess(sim_agua_diff, 0.45, f"500ml vs 1L deve sofrer penalidade: {sim_agua_diff}")

        # 4. Volumes equivalentes em unidades distintas (1000ml vs 1L)
        p_1000ml = PriceItem(source="s1", role="r", name="ÁGUA MINERAL CRISTAL 1000ML", url="u1")
        sim_agua_eq = similaridade_produto(p_1000ml, p_1l)
        self.assertGreaterEqual(sim_agua_eq, 0.90, f"1000ml vs 1L deve ter alta similaridade: {sim_agua_eq}")

        # 5. Produto com quantidade vs produto sem quantidade (conservador sem colapso)
        p_sem_unit = PriceItem(source="s1", role="r", name="ÁGUA MINERAL CRISTAL", url="u1")
        sim_sem_unit = similaridade_produto(p_sem_unit, p_1l)
        self.assertTrue(0.70 <= sim_sem_unit <= 0.90, f"Sem unit vs com unit deve manter similaridade moderada: {sim_sem_unit}")

        # 6. Planos/serviços com atributos numéricos distintos (ex: Plano 99 vs Plano 199)
        p_plano_99 = PriceItem(source="s1", role="r", name="PLANO PRO 99,90/MÊS", url="u1")
        p_plano_199 = PriceItem(source="s2", role="r", name="PLANO PRO 199,90/MÊS", url="u2")
        sim_planos_diff = similaridade_produto(p_plano_99, p_plano_199)
        self.assertLess(sim_planos_diff, 0.60, f"Planos de valores distintos devem sofrer deságio: {sim_planos_diff}")

        # 7. Planos idênticos
        sim_planos_iguais = similaridade_produto(p_plano_99, p_plano_99)
        self.assertGreaterEqual(sim_planos_iguais, 0.90, f"Planos idênticos devem ter alta similaridade: {sim_planos_iguais}")

    def test_20_identity_agnostic_conflict_policy(self):
        """Testa o comportamento agnóstico de identidade_conflitante com e sem políticas de exclusão injetadas."""
        from domain.identity import identidade_conflitante

        # 1. Sem política configurada -> agnóstico puro (nunca inventa conflito)
        self.assertFalse(identidade_conflitante("M Carvalho & Cia Loja de Ferramentas", empresa_alvo="Carvalho"))
        self.assertFalse(identidade_conflitante("Hospital Veterinário Santa Clara", empresa_alvo="Hospital Santa Clara"))

        # 2. Com política configurada para Carvalho (varejo alimentar vs ferramentas/construção)
        termos_carvalho = ["loja de ferramentas", "material de construcao", "ferramentas"]
        self.assertTrue(identidade_conflitante("M Carvalho & Cia Loja de Ferramentas em Teresina", termos_conflitantes=termos_carvalho))
        self.assertTrue(identidade_conflitante("Carvalho Material de Construcao e Tintas", termos_conflitantes=termos_carvalho))
        self.assertFalse(identidade_conflitante("Supermercado Carvalho Ofertas da Semana", termos_conflitantes=termos_carvalho))

        # 3. Com política configurada para outro nicho (ex: Hospital Humano vs Clínica Veterinária / Pet Shop)
        termos_hospital = ["veterinaria", "veterinario", "pet shop", "agropecuaria"]
        self.assertTrue(identidade_conflitante("Clinica Veterinaria Santa Clara 24h", termos_conflitantes=termos_hospital))
        self.assertFalse(identidade_conflitante("Hospital Santa Clara Pronto Socorro", termos_conflitantes=termos_hospital))


if __name__ == "__main__":
    unittest.main()
