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

        ocr_dir = (Path("fixtures/canonical_replay/ocr_bruto") if Path("fixtures/canonical_replay/ocr_bruto").exists() else Path("dados_browser/ocr_bruto"))
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

    def test_21_isolated_anchor_preservation(self):
        """Testa que âncoras monetárias isoladas não são descartadas e preservam o texto da âncora sem fabricar nomes."""
        from extractors.models import BoundingBox, SpatialToken, RawSpatialDocument
        from extractors.candidates import StrictCurrencyRule, CandidateDetector
        from extractors.clustering import clusterizar_espacialmente
        from extractors.adapters.flyer_product_adapter import FlyerProductResolver

        dim = (1000.0, 1000.0)

        # 1. Âncora isolada válida EXPLICIT_CURRENCY gera região e entidade
        doc_isolado = RawSpatialDocument("doc_iso", "banner", dim, [
            SpatialToken("R$ 99,00", BoundingBox(100.0, 100.0, 300.0, 150.0), id_token=1)
        ])
        det = CandidateDetector([StrictCurrencyRule()])
        ancoras_iso = det.detect_anchors(doc_isolado)
        self.assertEqual(len(ancoras_iso), 1)

        regioes_iso = clusterizar_espacialmente(doc_isolado, ancoras_iso)
        self.assertEqual(len(regioes_iso), 1, "Âncora isolada não pode ser descartada pelo clustering")

        resolver = FlyerProductResolver()
        ent_iso = resolver.resolve_region(regioes_iso[0])
        self.assertIsNotNone(ent_iso)
        self.assertEqual(ent_iso.valor, 99.00)
        self.assertEqual(ent_iso.atributos.get("nome"), "R$ 99,00", "Preserva o texto da âncora como contexto sem fabricar produto inexistente")

        # 2. Documento sem âncoras válidas continua sem regiões
        doc_sem_ancora = RawSpatialDocument("doc_vazio", "banner", dim, [
            SpatialToken("APENAS TEXTO SEM PRECO", BoundingBox(100.0, 100.0, 400.0, 150.0), id_token=1)
        ])
        ancoras_vazio = det.detect_anchors(doc_sem_ancora)
        self.assertEqual(len(ancoras_vazio), 0)
        regioes_vazio = clusterizar_espacialmente(doc_sem_ancora, ancoras_vazio)
        self.assertEqual(len(regioes_vazio), 0)

        # 3. Âncora com contexto textual continua extraindo nome adequadamente
        doc_com_contexto = RawSpatialDocument("doc_ctx", "flyer", dim, [
            SpatialToken("ARROZ TIO JOAO 5KG", BoundingBox(100.0, 100.0, 400.0, 130.0), id_token=1),
            SpatialToken("R$ 29,90", BoundingBox(100.0, 140.0, 250.0, 170.0), id_token=2),
        ])
        ancoras_ctx = det.detect_anchors(doc_com_contexto)
        regioes_ctx = clusterizar_espacialmente(doc_com_contexto, ancoras_ctx)
        self.assertEqual(len(regioes_ctx), 1)
        ent_ctx = resolver.resolve_region(regioes_ctx[0])
        self.assertIsNotNone(ent_ctx)
        self.assertEqual(ent_ctx.valor, 29.90)
        self.assertIn("ARROZ TIO JOAO", ent_ctx.atributos.get("nome"))

    def test_22_canary_generic_only_adversarial_suite(self):
        """Testes adversariais obrigatórios (Testes 1 a 8) da política estrita do Canary."""
        from pathlib import Path
        from unittest.mock import patch
        from domain.models import PriceItem
        from extractors.canary import comparar_documento_canary, CanaryDocumentReport
        from extractors.promotion_gate import PromotionGate

        # TESTE 1 — FANTASMA PLAUSÍVEL
        item_fantasma_plausivel = PriceItem(
            source="Assai", role="competitor", name="PRODUTO ABC", price=999.00, url="", price_confidence=0.95
        )
        rep1 = comparar_documento_canary(itens_legacy=[], itens_generic=[item_fantasma_plausivel])
        self.assertEqual(rep1.fp_generic, 1, "Generic-only fantasma plausível deve ser estritamente FP_GENERIC")
        self.assertEqual(rep1.fn_legacy, 0, "Generic-only não pode incrementar FN_LEGACY sem evidência independente")

        # TESTE 2 — FANTASMA SEMÂNTICO
        item_fantasma_semantico = PriceItem(
            source="Assai", role="competitor", name="ARROZ PREMIUM", price=20.79, url="", price_confidence=0.99
        )
        rep2 = comparar_documento_canary(itens_legacy=[], itens_generic=[item_fantasma_semantico])
        self.assertEqual(rep2.fp_generic, 1, "Generic-only com nome de produto semântico deve ser FP_GENERIC")
        self.assertEqual(rep2.fn_legacy, 0)

        # TESTE 3 — CONFIANÇA NÃO PODE TRANSFORMAR CLASSIFICAÇÃO
        for conf in [0.40, 0.60, 0.90, 0.99]:
            item_conf = PriceItem(
                source="Assai", role="competitor", name="PRODUTO FANTASMA", price=100.0, url="", price_confidence=conf
            )
            rep3 = comparar_documento_canary(itens_legacy=[], itens_generic=[item_conf])
            self.assertEqual(rep3.fp_generic, 1, f"Confiança {conf} não pode converter FP_GENERIC em FN_LEGACY")
            self.assertEqual(rep3.fn_legacy, 0)

        # TESTE 4 — NOME SEMÂNTICO MULTI-NICHO NÃO É PROVA
        nomes_multi_nicho = ["ARROZ PREMIUM", "TELEVISOR 50", "PLANO PREMIUM", "ACADEMIA GOLD"]
        for nome_nicho in nomes_multi_nicho:
            item_nicho = PriceItem(
                source="Competitor", role="competitor", name=nome_nicho, price=49.90, url="", price_confidence=0.95
            )
            rep4 = comparar_documento_canary(itens_legacy=[], itens_generic=[item_nicho])
            self.assertEqual(rep4.fp_generic, 1, f"Nome multi-nicho '{nome_nicho}' sem baseline deve ser FP_GENERIC")
            self.assertEqual(rep4.fn_legacy, 0)

        # TESTE 5 — MATCH
        l_item = PriceItem(source="Assai", role="competitor", name="ARROZ TIO JOAO 5KG", price=29.90, url="", unit="5kg")
        g_item = PriceItem(source="Assai", role="competitor", name="ARROZ TIO JOAO 5KG", price=29.90, url="", unit="5kg")
        rep5 = comparar_documento_canary(itens_legacy=[l_item], itens_generic=[g_item])
        self.assertEqual(rep5.matches_exatos, 1)
        self.assertEqual(rep5.fp_generic, 0)
        self.assertEqual(rep5.fn_legacy, 0)

        # TESTE 6 — LEGACY-ONLY (FN_GENERIC)
        l_only = PriceItem(source="Assai", role="competitor", name="LEITE INTEGRAL 1L", price=4.99, url="", unit="1l")
        rep6 = comparar_documento_canary(itens_legacy=[l_only], itens_generic=[])
        self.assertEqual(rep6.fn_generic, 1, "Item existente apenas no Legacy deve ser FN_GENERIC")
        self.assertEqual(rep6.fp_generic, 0)
        self.assertEqual(rep6.fn_legacy, 0)

        # TESTE 7 — PROMOTION GATE DETECTA FP_GENERIC (G2_fp_generic FAIL)
        gate = PromotionGate(min_documents_threshold=1)
        with patch("extractors.promotion_gate.comparar_documento_canary") as mock_canary:
            mock_rep = CanaryDocumentReport(documento_id="doc_fp", total_legacy=0, total_generic=1, fp_generic=1)
            mock_canary.return_value = mock_rep
            ocr_files = sorted(list((Path("fixtures/canonical_replay/ocr_bruto") if Path("fixtures/canonical_replay/ocr_bruto").exists() else Path("dados_browser/ocr_bruto")).glob("*.json")))
            res_gate = gate.evaluate(ocr_files[:1])
            self.assertEqual(res_gate.decision, "FAIL")
            self.assertEqual(res_gate.gates["G2_fp_generic"]["status"], "FAIL")
            self.assertGreater(res_gate.fp_generic, 0)

        # TESTE 8 — AUSÊNCIA DE HARDCODE DE PREÇOS NO CANARY
        import inspect
        import extractors.canary as canary_mod
        canary_source = inspect.getsource(canary_mod)
        for preco_hardcode in ["162.49", "156.80", "162.40"]:
            self.assertNotIn(preco_hardcode, canary_source, f"Preço hardcoded {preco_hardcode} encontrado no módulo canary")

    def test_23_decoupled_general_spatial_adapter_p1_1(self):
        """P1.1: Valida que GeneralSpatialAdapter é desacoplado de zonas fixas de encarte enquanto FlyerProductAdapter preserva especialização."""
        from pathlib import Path
        from extractors.models import BoundingBox, SpatialToken, RawSpatialDocument
        from extractors.adapters import GeneralSpatialAdapter, FlyerProductAdapter
        from extractors.bridge import carregar_ocr_bruto, executar_pipeline_extracao

        dim = (1000.0, 1000.0)

        # A. Oferta válida em y < 0.12 (topo da página)
        doc_topo = RawSpatialDocument("doc_topo", "web", dim, [
            SpatialToken("SERVIÇO NO TOPO", BoundingBox(100.0, 30.0, 450.0, 70.0), 0.99, 1),
            SpatialToken("R$ 150,00", BoundingBox(100.0, 80.0, 250.0, 110.0), 0.99, 2),
        ])
        gen_ad = GeneralSpatialAdapter()
        fly_ad = FlyerProductAdapter()

        res_gen_topo = gen_ad.processar_documento(doc_topo)
        res_fly_topo = fly_ad.processar_documento(doc_topo)
        self.assertEqual(len(res_gen_topo.entidades), 1, "Generic deve preservar ofertas no topo (y < 0.12)")
        self.assertEqual(len(res_fly_topo.entidades), 0, "FlyerAdapter deve filtrar cabeçalho de tablóide")

        # B. Oferta válida em y > 0.88 (rodapé da página)
        doc_rodape = RawSpatialDocument("doc_rodape", "web", dim, [
            SpatialToken("SERVIÇO NO RODAPÉ", BoundingBox(100.0, 900.0, 450.0, 930.0), 0.99, 1),
            SpatialToken("R$ 80,00", BoundingBox(100.0, 940.0, 250.0, 970.0), 0.99, 2),
        ])
        res_gen_rod = gen_ad.processar_documento(doc_rodape)
        res_fly_rod = fly_ad.processar_documento(doc_rodape)
        self.assertEqual(len(res_gen_rod.entidades), 1, "Generic deve preservar ofertas no rodapé (y > 0.88)")
        self.assertEqual(len(res_fly_rod.entidades), 0, "FlyerAdapter deve filtrar rodapé de tablóide")

        # C. Academia com card no topo
        doc_acad = RawSpatialDocument("doc_acad_topo", "gym", dim, [
            SpatialToken("ACADEMIA GOLD", BoundingBox(100.0, 20.0, 400.0, 50.0), 0.99, 1),
            SpatialToken("MENSALIDADE", BoundingBox(100.0, 55.0, 300.0, 80.0), 0.95, 2),
            SpatialToken("R$ 129,90", BoundingBox(100.0, 85.0, 250.0, 115.0), 0.99, 3),
        ])
        res_acad = gen_ad.processar_documento(doc_acad)
        self.assertEqual(len(res_acad.entidades), 1)
        self.assertEqual(res_acad.entidades[0].valor, 129.90)
        self.assertIn("ACADEMIA GOLD", res_acad.entidades[0].atributos.get("nome"))

        # D. SaaS com card no topo
        doc_saas = RawSpatialDocument("doc_saas_topo", "saas", dim, [
            SpatialToken("PLANO STARTER", BoundingBox(100.0, 30.0, 400.0, 60.0), 0.99, 1),
            SpatialToken("R$ 49,90 / MÊS", BoundingBox(100.0, 65.0, 350.0, 100.0), 0.99, 2),
        ])
        res_saas = gen_ad.processar_documento(doc_saas)
        self.assertEqual(len(res_saas.entidades), 1)
        self.assertEqual(res_saas.entidades[0].valor, 49.90)
        self.assertIn("PLANO STARTER", res_saas.entidades[0].atributos.get("nome"))

        # E. Supermercado real via FlyerProductAdapter mantém 63/63 entidades
        ocr_files = sorted(list((Path("fixtures/canonical_replay/ocr_bruto") if Path("fixtures/canonical_replay/ocr_bruto").exists() else Path("dados_browser/ocr_bruto")).glob("*.json")))
        tot_super = sum(len(fly_ad.processar_documento(carregar_ocr_bruto(f)).entidades) for f in ocr_files)
        self.assertEqual(tot_super, 63, "Supermercado real deve manter estritamente 63 entidades canônicas")

    def test_24_valid_short_word_candidate_filtering_p1_2(self):
        """P1.2: Valida política genérica de termos curtos válidos (SPA, GYM, BOX, PET, YOGA, PIX) e descarte de ruído."""
        from extractors.models import BoundingBox, SpatialToken, RawSpatialDocument
        from extractors.adapters import GeneralSpatialAdapter

        dim = (1000.0, 1000.0)
        ad = GeneralSpatialAdapter()

        # 1. Termos curtos válidos (SPA, GYM, BOX, PET, YOGA, PIX)
        short_names = [
            ("SPA RELAXANTE", 120.0),
            ("GYM PASS", 89.90),
            ("BOX CROSSFIT", 150.0),
            ("PET BANHO E TOSA", 65.0),
            ("YOGA MATINAL", 90.0),
            ("PIX DESCONTO", 45.0),
        ]
        for name, price in short_names:
            doc = RawSpatialDocument(f"doc_{name}", "test", dim, [
                SpatialToken(name, BoundingBox(100.0, 200.0, 400.0, 240.0), 0.99, 1),
                SpatialToken(f"R$ {price:.2f}".replace('.', ','), BoundingBox(100.0, 250.0, 250.0, 290.0), 0.99, 2),
            ])
            res = ad.processar_documento(doc)
            self.assertEqual(len(res.entidades), 1, f"Falha ao extrair entidade com nome curto '{name}'")
            self.assertIn(name.split()[0], res.entidades[0].atributos.get("nome"))

        # 2. Descarte de ruído puro (símbolos, datas, percentuais, CNPJs, preposições isoladas)
        noise_doc = RawSpatialDocument("doc_noise", "test", dim, [
            SpatialToken("---", BoundingBox(100.0, 100.0, 150.0, 130.0), 0.99, 1),
            SpatialToken("15/08/2026", BoundingBox(100.0, 140.0, 250.0, 170.0), 0.99, 2),
            SpatialToken("25%", BoundingBox(100.0, 180.0, 180.0, 210.0), 0.99, 3),
            SpatialToken("12.345.678/0001-90", BoundingBox(100.0, 220.0, 350.0, 250.0), 0.99, 4),
            SpatialToken("R$ 50,00", BoundingBox(100.0, 300.0, 250.0, 340.0), 0.99, 5),
        ])
        res_noise = ad.processar_documento(noise_doc)
        self.assertEqual(len(res_noise.entidades), 1)
        # O nome extraído não pode ser o CNPJ, data, percentual ou traços
        nome_extraido = res_noise.entidades[0].atributos.get("nome")
        self.assertNotIn("12.345.678", nome_extraido)
        self.assertNotIn("15/08", nome_extraido)
        self.assertNotIn("25%", nome_extraido)
        self.assertNotIn("---", nome_extraido)

    def test_25_multi_nicho_dominance_and_case1_mandatory_suite(self):
        """Fase 15: Bateria obrigatória de 10 cenários multi-nicho de dominância e Caso 1 real."""
        from extractors.models import BoundingBox, SpatialToken, RawSpatialDocument, AnchorEvidenceKind
        from extractors.adapters import GeneralSpatialAdapter, FlyerProductAdapter
        from extractors.bridge import carregar_ocr_bruto
        from pathlib import Path
        import json

        dim = (2000.0, 3000.0)
        ad = GeneralSpatialAdapter()

        # 1. Restaurante: Prato Executivo Filé — 59,90 (BARE_DECIMAL preservado)
        doc_rest = RawSpatialDocument("doc_rest", "restaurant", dim, [
            SpatialToken("PRATO EXECUTIVO FILÉ", BoundingBox(100.0, 200.0, 450.0, 230.0), 0.99, 1),
            SpatialToken("59,90", BoundingBox(100.0, 240.0, 200.0, 270.0), 0.99, 2),
        ])
        res_rest = ad.processar_documento(doc_rest)
        self.assertEqual(len(res_rest.entidades), 1)
        self.assertEqual(res_rest.entidades[0].valor, 59.90)
        self.assertIn("PRATO EXECUTIVO", res_rest.entidades[0].atributos.get("nome"))

        # 2. Hotel: Suíte — 2 diárias — R$ 350,00 (Preço R$ 350,00)
        doc_hotel = RawSpatialDocument("doc_hotel", "hotel", dim, [
            SpatialToken("SUÍTE MASTER", BoundingBox(100.0, 200.0, 350.0, 230.0), 0.99, 1),
            SpatialToken("2 DIÁRIAS", BoundingBox(100.0, 240.0, 250.0, 265.0), 0.95, 2),
            SpatialToken("R$ 350,00", BoundingBox(100.0, 275.0, 250.0, 305.0), 0.99, 3),
        ])
        res_hotel = ad.processar_documento(doc_hotel)
        self.assertEqual(len(res_hotel.entidades), 1)
        self.assertEqual(res_hotel.entidades[0].valor, 350.00)

        # 3. Clínica: Tratamento — 10 sessões — R$ 180,00 (Preço R$ 180,00)
        doc_clin = RawSpatialDocument("doc_clin", "clinic", dim, [
            SpatialToken("TRATAMENTO FISIOTERAPIA", BoundingBox(100.0, 200.0, 450.0, 230.0), 0.99, 1),
            SpatialToken("10 SESSÕES", BoundingBox(100.0, 240.0, 250.0, 265.0), 0.95, 2),
            SpatialToken("R$ 180,00", BoundingBox(100.0, 275.0, 250.0, 305.0), 0.99, 3),
        ])
        res_clin = ad.processar_documento(doc_clin)
        self.assertEqual(len(res_clin.entidades), 1)
        self.assertEqual(res_clin.entidades[0].valor, 180.00)

        # 4. Coincidência: Pacote 10 sessões — 10,00 (Preço 10,00 preservado)
        doc_coinc = RawSpatialDocument("doc_coinc", "clinic", dim, [
            SpatialToken("PACOTE PROMOCIONAL", BoundingBox(100.0, 200.0, 400.0, 230.0), 0.99, 1),
            SpatialToken("10 SESSÕES", BoundingBox(100.0, 240.0, 250.0, 265.0), 0.95, 2),
            SpatialToken("10,00", BoundingBox(100.0, 275.0, 200.0, 305.0), 0.99, 3),
        ])
        res_coinc = ad.processar_documento(doc_coinc)
        self.assertEqual(len(res_coinc.entidades), 1)
        self.assertEqual(res_coinc.entidades[0].valor, 10.00)

        # 5. SaaS: Plano Pro — 99,90/mês (CADENCE_PRICE)
        doc_saas = RawSpatialDocument("doc_saas", "saas", dim, [
            SpatialToken("PLANO PRO", BoundingBox(100.0, 200.0, 300.0, 230.0), 0.99, 1),
            SpatialToken("99,90/MÊS", BoundingBox(100.0, 240.0, 280.0, 270.0), 0.99, 2),
        ])
        res_saas = ad.processar_documento(doc_saas)
        self.assertEqual(len(res_saas.entidades), 1)
        self.assertEqual(res_saas.entidades[0].valor, 99.90)

        # 6. B2B: Proposta Comercial 2.026 — R$ 5.000,00 (Preço 5000,00)
        doc_b2b = RawSpatialDocument("doc_b2b", "b2b", dim, [
            SpatialToken("PROPOSTA COMERCIAL 2.026", BoundingBox(100.0, 200.0, 450.0, 230.0), 0.99, 1),
            SpatialToken("R$ 5.000,00", BoundingBox(100.0, 240.0, 300.0, 270.0), 0.99, 2),
        ])
        res_b2b = ad.processar_documento(doc_b2b)
        self.assertEqual(len(res_b2b.entidades), 1)
        self.assertEqual(res_b2b.entidades[0].valor, 5000.00)

        # 7. Caso 1 real: 49464_pagina_1.json (falso 162,49 eliminado; 20,79 CADA preservado; 9 entidades)
        path_caso1 = (Path("fixtures/canonical_replay/ocr_bruto/49464_pagina_1.json") if Path("fixtures/canonical_replay/ocr_bruto/49464_pagina_1.json").exists() else (Path("fixtures/canonical_replay/ocr_bruto/49464_pagina_1.json") if Path("fixtures/canonical_replay/ocr_bruto/49464_pagina_1.json").exists() else Path("dados_browser/ocr_bruto/49464_pagina_1.json")))
        if path_caso1.exists():
            doc_real_c1 = carregar_ocr_bruto(path_caso1)
            ad_flyer = FlyerProductAdapter()
            res_c1 = ad_flyer.processar_documento(doc_real_c1)
            self.assertEqual(len(res_c1.entidades), 9, "49464_pagina_1 deve conter exatamente 9 entidades legítimas")
            valores_c1 = [e.valor for e in res_c1.entidades]
            self.assertIn(20.79, valores_c1, "20.79 CADA deve ser preservado")
            self.assertNotIn(162.49, valores_c1, "Falso preço 162.49 não pode existir como entidade independente")

        # 8. Bare number isolado: vários valores legítimos continuam funcionando
        for bare_val in [23.90, 350.00, 59.90, 12.50]:
            doc_bare = RawSpatialDocument(f"doc_bare_{bare_val}", "bare", dim, [
                SpatialToken("SERVIÇO AVULSO", BoundingBox(100.0, 200.0, 350.0, 230.0), 0.99, 1),
                SpatialToken(f"{bare_val:.2f}".replace('.', ','), BoundingBox(100.0, 240.0, 220.0, 270.0), 0.99, 2),
            ])
            res_bare = ad.processar_documento(doc_bare)
            self.assertEqual(len(res_bare.entidades), 1)
            self.assertEqual(res_bare.entidades[0].valor, bare_val)

        # 9. Duas ofertas próximas: dominância não atravessa regiões distintas
        doc_duas = RawSpatialDocument("doc_duas", "test", dim, [
            # Oferta 1 (Card Esquerdo)
            SpatialToken("PRODUTO ALFA", BoundingBox(100.0, 200.0, 350.0, 230.0), 0.99, 1),
            SpatialToken("R$ 100,00", BoundingBox(100.0, 240.0, 250.0, 270.0), 0.99, 2),
            # Oferta 2 (Card Direito)
            SpatialToken("PRODUTO BETA", BoundingBox(600.0, 200.0, 850.0, 230.0), 0.99, 3),
            SpatialToken("50,00", BoundingBox(600.0, 240.0, 720.0, 270.0), 0.99, 4),
        ])
        res_duas = ad.processar_documento(doc_duas)
        self.assertEqual(len(res_duas.entidades), 2, "Duas ofertas distintas não podem colapsar por dominância errônea")
        precos_duas = sorted([e.valor for e in res_duas.entidades])
        self.assertEqual(precos_duas, [50.00, 100.00])

        # 10. Determinismo: mesma entrada produz exatamente a mesma saída
        if path_caso1.exists():
            res_det_1 = [e.to_dict() for e in ad_flyer.processar_documento(doc_real_c1).entidades]
            res_det_2 = [e.to_dict() for e in ad_flyer.processar_documento(doc_real_c1).entidades]
            self.assertEqual(
                json.dumps(res_det_1, sort_keys=True),
                json.dumps(res_det_2, sort_keys=True),
                "Execução do pipeline deve ser estritamente determinística"
            )

    def test_26_p2_2_depor_promotional_offers_multi_niche(self):
        """Fase 16 (P2.2): Validação abrangente de ofertas promocionais De/Por em múltiplos nichos e anti-overfitting."""
        from extractors.models import BoundingBox, SpatialToken, RawSpatialDocument, AnchorRole
        from extractors.adapters import GeneralSpatialAdapter, FlyerProductAdapter
        from extractors.bridge import converter_entidades_para_price_items

        dim = (2000.0, 3000.0)
        ad = GeneralSpatialAdapter()

        # 1. Restaurante: De R$ 79,90 Por R$ 59,90
        doc_rest = RawSpatialDocument("doc_rest", "restaurant", dim, [
            SpatialToken("PRATO ESPECIAL PICANHA", BoundingBox(100.0, 200.0, 450.0, 230.0), 0.99, 1),
            SpatialToken("De R$ 79,90", BoundingBox(100.0, 240.0, 250.0, 265.0), 0.99, 2),
            SpatialToken("Por R$ 59,90", BoundingBox(100.0, 270.0, 250.0, 300.0), 0.99, 3),
        ])
        res_rest = ad.processar_documento(doc_rest)
        self.assertEqual(len(res_rest.entidades), 1)
        ent_rest = res_rest.entidades[0]
        self.assertEqual(ent_rest.valor, 59.90)
        self.assertEqual(ent_rest.old_price, 79.90)
        self.assertTrue(ent_rest.atributos.get("promocao"))

        # 2. Hotel: Diária: De R$ 500,00 Por R$ 350,00
        doc_hotel = RawSpatialDocument("doc_hotel", "hotel", dim, [
            SpatialToken("DIÁRIA SUÍTE MASTER", BoundingBox(100.0, 200.0, 400.0, 230.0), 0.99, 1),
            SpatialToken("De R$ 500,00", BoundingBox(100.0, 240.0, 260.0, 265.0), 0.99, 2),
            SpatialToken("Por R$ 350,00", BoundingBox(100.0, 270.0, 260.0, 300.0), 0.99, 3),
        ])
        res_hotel = ad.processar_documento(doc_hotel)
        self.assertEqual(len(res_hotel.entidades), 1)
        self.assertEqual(res_hotel.entidades[0].valor, 350.00)
        self.assertEqual(res_hotel.entidades[0].old_price, 500.00)

        # 3. Clínica: Tratamento: De R$ 1.000,00 Por R$ 799,90
        doc_clin = RawSpatialDocument("doc_clin", "clinic", dim, [
            SpatialToken("TRATAMENTO ESTÉTICO", BoundingBox(100.0, 200.0, 450.0, 230.0), 0.99, 1),
            SpatialToken("De R$ 1.000,00", BoundingBox(100.0, 240.0, 280.0, 265.0), 0.99, 2),
            SpatialToken("Por R$ 799,90", BoundingBox(100.0, 270.0, 280.0, 300.0), 0.99, 3),
        ])
        res_clin = ad.processar_documento(doc_clin)
        self.assertEqual(len(res_clin.entidades), 1)
        self.assertEqual(res_clin.entidades[0].valor, 799.90)
        self.assertEqual(res_clin.entidades[0].old_price, 1000.00)

        # 4. SaaS: Plano Pro: De R$ 199,90/mês Por R$ 149,90/mês
        doc_saas = RawSpatialDocument("doc_saas", "saas", dim, [
            SpatialToken("PLANO ENTERPRISE", BoundingBox(100.0, 200.0, 400.0, 230.0), 0.99, 1),
            SpatialToken("De R$ 199,90/mês", BoundingBox(100.0, 240.0, 300.0, 265.0), 0.99, 2),
            SpatialToken("Por R$ 149,90/mês", BoundingBox(100.0, 270.0, 300.0, 300.0), 0.99, 3),
        ])
        res_saas = ad.processar_documento(doc_saas)
        self.assertEqual(len(res_saas.entidades), 1)
        self.assertEqual(res_saas.entidades[0].valor, 149.90)
        self.assertEqual(res_saas.entidades[0].old_price, 199.90)

        # 5. B2B: Contrato: De R$ 10.000,00 Por R$ 8.500,00
        doc_b2b = RawSpatialDocument("doc_b2b", "b2b", dim, [
            SpatialToken("CONTRATO ANUAL CONSULTORIA", BoundingBox(100.0, 200.0, 450.0, 230.0), 0.99, 1),
            SpatialToken("De R$ 10.000,00", BoundingBox(100.0, 240.0, 300.0, 265.0), 0.99, 2),
            SpatialToken("Por R$ 8.500,00", BoundingBox(100.0, 270.0, 300.0, 300.0), 0.99, 3),
        ])
        res_b2b = ad.processar_documento(doc_b2b)
        self.assertEqual(len(res_b2b.entidades), 1)
        self.assertEqual(res_b2b.entidades[0].valor, 8500.00)
        self.assertEqual(res_b2b.entidades[0].old_price, 10000.00)

        # 6. Bare com marcador: De 100,00 Por 79,90
        doc_bare_depor = RawSpatialDocument("doc_bare_depor", "retail", dim, [
            SpatialToken("PRODUTO BARE PROMOÇÃO", BoundingBox(100.0, 200.0, 450.0, 230.0), 0.99, 1),
            SpatialToken("De 100,00", BoundingBox(100.0, 240.0, 220.0, 265.0), 0.99, 2),
            SpatialToken("Por 79,90", BoundingBox(100.0, 270.0, 220.0, 300.0), 0.99, 3),
        ])
        res_bare_depor = ad.processar_documento(doc_bare_depor)
        self.assertEqual(len(res_bare_depor.entidades), 1)
        self.assertEqual(res_bare_depor.entidades[0].valor, 79.90)
        self.assertEqual(res_bare_depor.entidades[0].old_price, 100.00)

        # 7. Centavos: De R$ 100,00 Por R$ 99,99
        doc_cent = RawSpatialDocument("doc_cent", "retail", dim, [
            SpatialToken("PRODUTO DESCONTO MÍNIMO", BoundingBox(100.0, 200.0, 450.0, 230.0), 0.99, 1),
            SpatialToken("De R$ 100,00", BoundingBox(100.0, 240.0, 250.0, 265.0), 0.99, 2),
            SpatialToken("Por R$ 99,99", BoundingBox(100.0, 270.0, 250.0, 300.0), 0.99, 3),
        ])
        res_cent = ad.processar_documento(doc_cent)
        self.assertEqual(len(res_cent.entidades), 1)
        self.assertEqual(res_cent.entidades[0].valor, 99.99)
        self.assertEqual(res_cent.entidades[0].old_price, 100.00)

        # 8. OCR Fragmentado: ["De", "R$", "100,00", "Por", "R$", "79,90"]
        doc_frag = RawSpatialDocument("doc_frag_depor", "test", dim, [
            SpatialToken("PRODUTO FRAGMENTADO", BoundingBox(100.0, 200.0, 450.0, 230.0), 0.99, 1),
            SpatialToken("De", BoundingBox(100.0, 240.0, 130.0, 265.0), 0.99, 2),
            SpatialToken("R$", BoundingBox(135.0, 240.0, 160.0, 265.0), 0.99, 3),
            SpatialToken("100,00", BoundingBox(165.0, 240.0, 240.0, 265.0), 0.99, 4),
            SpatialToken("Por", BoundingBox(100.0, 270.0, 135.0, 295.0), 0.99, 5),
            SpatialToken("R$", BoundingBox(140.0, 270.0, 165.0, 295.0), 0.99, 6),
            SpatialToken("79,90", BoundingBox(170.0, 270.0, 240.0, 295.0), 0.99, 7),
        ])
        res_frag = ad.processar_documento(doc_frag)
        self.assertEqual(len(res_frag.entidades), 1)
        self.assertEqual(res_frag.entidades[0].valor, 79.90)
        self.assertEqual(res_frag.entidades[0].old_price, 100.00)
        self.assertTrue(res_frag.entidades[0].atributos.get("promocao"))

        # 9. Anti-Overfitting 1: R$ 100,00 e R$ 79,90 sem marcador -> 2 entidades independentes
        doc_sem_marc = RawSpatialDocument("doc_sem_marc", "test", dim, [
            SpatialToken("PRODUTO ALFA", BoundingBox(100.0, 200.0, 350.0, 230.0), 0.99, 1),
            SpatialToken("R$ 100,00", BoundingBox(100.0, 240.0, 250.0, 265.0), 0.99, 2),
            SpatialToken("R$ 79,90", BoundingBox(100.0, 275.0, 250.0, 300.0), 0.99, 3),
        ])
        res_sem_marc = ad.processar_documento(doc_sem_marc)
        self.assertEqual(len(res_sem_marc.entidades), 2, "Sem marcador relacional, NÃO inventar promoção!")
        for e in res_sem_marc.entidades:
            self.assertIsNone(e.old_price)
            self.assertFalse(e.atributos.get("promocao", False))

        # 10. Anti-Overfitting 2: Cards vizinhos distintos com De/Por independentes
        doc_vizinhos = RawSpatialDocument("doc_vizinhos", "test", dim, [
            # Card 1 (Esquerda)
            SpatialToken("PRODUTO A", BoundingBox(100.0, 200.0, 350.0, 230.0), 0.99, 1),
            SpatialToken("De R$ 100,00", BoundingBox(100.0, 240.0, 250.0, 265.0), 0.99, 2),
            SpatialToken("Por R$ 80,00", BoundingBox(100.0, 270.0, 250.0, 295.0), 0.99, 3),
            # Card 2 (Direita)
            SpatialToken("PRODUTO B", BoundingBox(600.0, 200.0, 850.0, 230.0), 0.99, 4),
            SpatialToken("De R$ 200,00", BoundingBox(600.0, 240.0, 750.0, 265.0), 0.99, 5),
            SpatialToken("Por R$ 150,00", BoundingBox(600.0, 270.0, 750.0, 295.0), 0.99, 6),
        ])
        res_vizinhos = ad.processar_documento(doc_vizinhos)
        self.assertEqual(len(res_vizinhos.entidades), 2, "Cards vizinhos devem manter suas próprias promoções")
        v_a = next(e for e in res_vizinhos.entidades if "PRODUTO A" in e.atributos.get("nome", "").upper())
        v_b = next(e for e in res_vizinhos.entidades if "PRODUTO B" in e.atributos.get("nome", "").upper())
        self.assertEqual(v_a.valor, 80.00)
        self.assertEqual(v_a.old_price, 100.00)
        self.assertEqual(v_b.valor, 150.00)
        self.assertEqual(v_b.old_price, 200.00)

        # 11. Conversão Bridge downstream: PriceItem recebe price, old_price e promotion
        items = converter_entidades_para_price_items(res_rest.entidades)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].price, 59.90)
        self.assertEqual(items[0].old_price, 79.90)
        self.assertTrue(items[0].promotion)

    def test_27_p2_1_adaptive_line_clustering_and_tables(self):
        """Fase 17 (P2.1): Validação abrangente de clustering adaptativo para estruturas tabulares, linhas e isolamento."""
        from pathlib import Path
        from extractors.models import BoundingBox, SpatialToken, RawSpatialDocument
        from extractors.adapters import GeneralSpatialAdapter, FlyerProductAdapter
        from extractors.bridge import carregar_ocr_bruto

        dim = (2000.0, 1000.0)
        ad = GeneralSpatialAdapter()

        # 1. Tabela horizontal com 3 produtos (Produto A, B, C)
        doc1 = RawSpatialDocument("doc1", "test", dim, [
            SpatialToken("Produto Alfa Especial", BoundingBox(100.0, 100.0, 500.0, 140.0), 0.99, 1),
            SpatialToken("R$ 59,90", BoundingBox(1600.0, 100.0, 1800.0, 140.0), 0.99, 2),
            SpatialToken("Produto Beta Premium", BoundingBox(100.0, 200.0, 500.0, 240.0), 0.99, 3),
            SpatialToken("R$ 79,90", BoundingBox(1600.0, 200.0, 1800.0, 240.0), 0.99, 4),
            SpatialToken("Produto Gama Master", BoundingBox(100.0, 300.0, 500.0, 340.0), 0.99, 5),
            SpatialToken("R$ 99,90", BoundingBox(1600.0, 300.0, 1800.0, 340.0), 0.99, 6),
        ])
        res1 = ad.processar_documento(doc1)
        self.assertEqual(len(res1.entidades), 3)
        self.assertIn("ALFA", res1.entidades[0].atributos.get("nome", "").upper())
        self.assertEqual(res1.entidades[0].valor, 59.90)
        self.assertIn("BETA", res1.entidades[1].atributos.get("nome", "").upper())
        self.assertEqual(res1.entidades[1].valor, 79.90)
        self.assertIn("GAMA", res1.entidades[2].atributos.get("nome", "").upper())
        self.assertEqual(res1.entidades[2].valor, 99.90)

        # 2. Grande distância horizontal (dx > 0.40 * W) na mesma linha
        doc2 = RawSpatialDocument("doc2", "test", dim, [
            SpatialToken("Plano Enterprise Anual", BoundingBox(50.0, 100.0, 350.0, 140.0), 0.99, 1),
            SpatialToken("R$ 499,00", BoundingBox(1800.0, 100.0, 1950.0, 140.0), 0.99, 2),
        ])
        res2 = ad.processar_documento(doc2)
        self.assertEqual(len(res2.entidades), 1)
        self.assertIn("ENTERPRISE", res2.entidades[0].atributos.get("nome", "").upper())
        self.assertEqual(res2.entidades[0].valor, 499.00)

        # 3. Linhas diferentes: descrição de uma linha não associa com preço de outra linha
        doc3 = RawSpatialDocument("doc3", "test", dim, [
            SpatialToken("Descrição Linha 1", BoundingBox(100.0, 100.0, 400.0, 130.0), 0.99, 1),
            SpatialToken("R$ 10,00", BoundingBox(1600.0, 100.0, 1750.0, 130.0), 0.99, 2),
            SpatialToken("Descrição Linha 2", BoundingBox(100.0, 300.0, 400.0, 330.0), 0.99, 3),
            SpatialToken("R$ 20,00", BoundingBox(1600.0, 300.0, 1750.0, 330.0), 0.99, 4),
        ])
        res3 = ad.processar_documento(doc3)
        self.assertEqual(len(res3.entidades), 2)
        self.assertIn("Linha 1", res3.entidades[0].atributos.get("nome", ""))
        self.assertIn("Linha 2", res3.entidades[1].atributos.get("nome", ""))

        # 4. Cards vizinhos independentes
        doc4 = RawSpatialDocument("doc4", "test", dim, [
            SpatialToken("Produto Card A", BoundingBox(100.0, 100.0, 300.0, 130.0), 0.99, 1),
            SpatialToken("R$ 100,00", BoundingBox(100.0, 140.0, 200.0, 170.0), 0.99, 2),
            SpatialToken("Produto Card B", BoundingBox(600.0, 100.0, 800.0, 130.0), 0.99, 3),
            SpatialToken("R$ 50,00", BoundingBox(600.0, 140.0, 700.0, 170.0), 0.99, 4),
        ])
        res4 = ad.processar_documento(doc4)
        self.assertEqual(len(res4.entidades), 2)
        self.assertIn("CARD A", res4.entidades[0].atributos.get("nome", "").upper())
        self.assertEqual(res4.entidades[0].valor, 100.00)
        self.assertIn("CARD B", res4.entidades[1].atributos.get("nome", "").upper())
        self.assertEqual(res4.entidades[1].valor, 50.00)

        # 5. Múltiplas âncoras na mesma linha (não atravessa âncora intermediária)
        doc5 = RawSpatialDocument("doc5", "test", dim, [
            SpatialToken("Item 1", BoundingBox(50.0, 100.0, 200.0, 130.0), 0.99, 1),
            SpatialToken("R$ 10,00", BoundingBox(250.0, 100.0, 350.0, 130.0), 0.99, 2),
            SpatialToken("Item 2", BoundingBox(600.0, 100.0, 750.0, 130.0), 0.99, 3),
            SpatialToken("R$ 20,00", BoundingBox(800.0, 100.0, 900.0, 130.0), 0.99, 4),
        ])
        res5 = ad.processar_documento(doc5)
        self.assertEqual(len(res5.entidades), 2)
        self.assertIn("Item 1", res5.entidades[0].atributos.get("nome", ""))
        self.assertEqual(res5.entidades[0].valor, 10.00)
        self.assertIn("Item 2", res5.entidades[1].atributos.get("nome", ""))
        self.assertEqual(res5.entidades[1].valor, 20.00)

        # 6. OCR fragmentado na tabela
        doc6 = RawSpatialDocument("doc6", "test", dim, [
            SpatialToken("Prato Especial", BoundingBox(100.0, 100.0, 250.0, 130.0), 0.99, 1),
            SpatialToken("do Chef", BoundingBox(260.0, 100.0, 380.0, 130.0), 0.99, 2),
            SpatialToken("R$ 85,00", BoundingBox(1600.0, 100.0, 1750.0, 130.0), 0.99, 3),
        ])
        res6 = ad.processar_documento(doc6)
        self.assertEqual(len(res6.entidades), 1)
        self.assertIn("Prato Especial", res6.entidades[0].atributos.get("nome", ""))
        self.assertIn("do Chef", res6.entidades[0].atributos.get("nome", ""))
        self.assertEqual(res6.entidades[0].valor, 85.00)

        # 7. Invariância geométrica de escala
        for escala in [0.5, 1.0, 2.0, 4.0]:
            tokens_s = [
                SpatialToken(t.texto, BoundingBox(t.bbox.x_min * escala, t.bbox.y_min * escala, t.bbox.x_max * escala, t.bbox.y_max * escala), t.confianca, t.id_token)
                for t in doc1.tokens
            ]
            doc_s = RawSpatialDocument("doc_s", "test", (dim[0] * escala, dim[1] * escala), tokens_s)
            res_s = ad.processar_documento(doc_s)
            self.assertEqual(len(res_s.entidades), 3, f"Falha na escala {escala}")

        # 8. Regressão Caso 1 Real (162,49 eliminado vs 20,79 preço vigente)
        ad_flyer = FlyerProductAdapter()
        path_c1 = Path(r"dados_browser/ocr_bruto\49464_pagina_1.json")
        if path_c1.exists():
            doc_c1 = carregar_ocr_bruto(path_c1)
            res_c1 = ad_flyer.processar_documento(doc_c1)
            precos_c1 = [e.valor for e in res_c1.entidades]
            self.assertIn(20.79, precos_c1)
            self.assertNotIn(162.49, precos_c1)

        # 9. Regressão Fase 16 (De/Por + old_price)
        doc_depor = RawSpatialDocument("doc_dp", "test", dim, [
            SpatialToken("PRODUTO PROMO", BoundingBox(100.0, 200.0, 400.0, 230.0), 0.99, 1),
            SpatialToken("De R$ 100,00", BoundingBox(100.0, 240.0, 250.0, 265.0), 0.99, 2),
            SpatialToken("Por R$ 79,90", BoundingBox(100.0, 270.0, 250.0, 295.0), 0.99, 3),
        ])
        res_dp = ad.processar_documento(doc_depor)
        self.assertEqual(len(res_dp.entidades), 1)
        self.assertEqual(res_dp.entidades[0].valor, 79.90)
        self.assertEqual(res_dp.entidades[0].old_price, 100.00)
        self.assertTrue(res_dp.entidades[0].atributos.get("promocao"))

        # 10. Isolamento de cards De/Por vizinhos
        doc_viz_dp = RawSpatialDocument("doc_vdp", "test", dim, [
            # Card A
            SpatialToken("CARD A", BoundingBox(100.0, 200.0, 350.0, 230.0), 0.99, 1),
            SpatialToken("De R$ 100,00", BoundingBox(100.0, 240.0, 250.0, 265.0), 0.99, 2),
            SpatialToken("Por R$ 80,00", BoundingBox(100.0, 270.0, 250.0, 295.0), 0.99, 3),
            # Card B
            SpatialToken("CARD B", BoundingBox(600.0, 200.0, 850.0, 230.0), 0.99, 4),
            SpatialToken("De R$ 200,00", BoundingBox(600.0, 240.0, 750.0, 265.0), 0.99, 5),
            SpatialToken("Por R$ 150,00", BoundingBox(600.0, 270.0, 750.0, 295.0), 0.99, 6),
        ])
        res_vdp = ad.processar_documento(doc_viz_dp)
        self.assertEqual(len(res_vdp.entidades), 2)
        ea = next(e for e in res_vdp.entidades if "CARD A" in e.atributos.get("nome", "").upper())
        eb = next(e for e in res_vdp.entidades if "CARD B" in e.atributos.get("nome", "").upper())
        self.assertEqual(ea.valor, 80.00)
        self.assertEqual(ea.old_price, 100.00)
        self.assertEqual(eb.valor, 150.00)
        self.assertEqual(eb.old_price, 200.00)


if __name__ == "__main__":
    unittest.main()
