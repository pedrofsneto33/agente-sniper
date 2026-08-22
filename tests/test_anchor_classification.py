# -*- coding: utf-8 -*-
"""
Bateria de Testes de Domínio — Classificação Genérica de Âncoras e Sinais.
Valida os 10 requisitos obrigatórios da Fase 52.
"""
import unittest
from domain.anchors import (
    AnchorClassification,
    GenericAnchorClassifier,
    classificar_ancora,
    classificar_texto_ancora,
    ANCHOR_PRECEDENCE,
    DEFAULT_ANCHOR_RULES,
    ANCHOR_ALIASES,
)
from domain.models import Fonte
from domain.events import _primary_event_kind
from domain.profiles import obter_perfil_nicho


class TestAnchorClassification(unittest.TestCase):
    """Testes unitários e de integração para a classificação genérica de âncoras."""

    def test_01_classificacao_ancoras_conhecidas(self):
        """1. Valida classificação correta de âncoras conhecidas em todas as 10 categorias canônicas."""
        amostras = {
            "REGULAÇÃO": "Procon autua estabelecimento por irregularidade em fiscalização",
            "PESSOAS": "Empresa abre 50 vagas de emprego para contratação imediata",
            "EXPANSÃO": "Rede anuncia inauguração de nova unidade e expansão no estado",
            "REPUTAÇÃO": "Consumidor registra reclamação e queixa no Reclame Aqui com nota baixa",
            "ATENDIMENTO": "Clientes relatam fila excessiva e demora no atendimento ao cliente",
            "PREÇO": "Supermercado divulga encarte com oferta especial e desconto no preço",
            "DIGITAL": "Lojas lançam novo aplicativo com delivery e plataforma de e-commerce",
            "MARKETING": "Marca inicia nova campanha de marketing com publicidade e patrocínio",
            "PRODUTO/SERVIÇO": "Restaurante traz novidade no cardápio e lançamento de produto novo",
            "PARCERIA": "Empresa firma parceria estratégica e acordo com novo fornecedor",
        }
        for cat_esperada, texto in amostras.items():
            with self.subTest(categoria=cat_esperada):
                cls = classificar_ancora(texto)
                self.assertTrue(cls.is_known)
                self.assertEqual(cls.category, cat_esperada)
                self.assertGreater(cls.confidence, 0.0)
                self.assertTrue(len(cls.matched_term) > 0)

    def test_02_classificacao_ancoras_desconhecidas(self):
        """2. Valida fallback seguro para textos e âncoras desconhecidas ou vazias."""
        textos_desconhecidos = [
            "",
            "   ",
            "Texto aleatório sem nenhum sinal ou âncora comercial",
            "Lorem ipsum dolor sit amet consectetur adipiscing elit",
            "123456789 987654321",
        ]
        for t in textos_desconhecidos:
            with self.subTest(texto=t):
                cls = classificar_ancora(t)
                self.assertFalse(cls.is_known)
                self.assertEqual(cls.category, "UNKNOWN")
                self.assertEqual(cls.confidence, 0.0)
                self.assertEqual(cls.matched_term, "")
                self.assertEqual(cls.secondary_categories, ())

    def test_03_normalizacao_e_insensibilidade_a_acentos_e_caixa(self):
        """3. Valida que normalização trata caixa alta/baixa, acentos e pontuação de forma idêntica."""
        t1 = "PROCON FISCALIZAÇÃO E MULTA"
        t2 = "procon fiscalizacao e multa"
        t3 = "PrOcOn FiScAlIzAçÃo E mUlTa!!!"

        c1 = classificar_ancora(t1)
        c2 = classificar_ancora(t2)
        c3 = classificar_ancora(t3)

        self.assertEqual(c1.category, "REGULAÇÃO")
        self.assertEqual(c2.category, "REGULAÇÃO")
        self.assertEqual(c3.category, "REGULAÇÃO")
        self.assertEqual(c1.confidence, c2.confidence)
        self.assertEqual(c2.confidence, c3.confidence)

    def test_04_aliases_e_variacoes_semanticas(self):
        """4. Valida resolução de aliases e termos coloquiais para categorias canônicas."""
        cls_promo = classificar_ancora("Confira a grande promo de hoje")
        self.assertEqual(cls_promo.category, "PREÇO")

        cls_reclama = classificar_ancora("Cliente reclama de problema")
        self.assertEqual(cls_reclama.category, "REPUTAÇÃO")

    def test_05_ausencia_de_falsos_positivos(self):
        """5. Valida que palavras neutras não disparam falsos positivos."""
        textos_neutros = [
            "O dia estava ensolarado na cidade",
            "Reunião de alinhamento interno da diretoria",
            "Documento técnico de arquitetura de software",
        ]
        for t in textos_neutros:
            with self.subTest(texto=t):
                cls = classificar_ancora(t)
                self.assertFalse(cls.is_known)
                self.assertEqual(cls.category, "UNKNOWN")

    def test_06_precedencia_determinística_com_multiplas_categorias(self):
        """6. Valida ordem estrita de precedência quando múltiplas categorias colidem no mesmo texto."""
        # Colisão entre REGULAÇÃO (prioridade 1) e PREÇO (prioridade 6)
        t_reg_preco = "Procon multa loja por propaganda enganosa no preço e oferta"
        cls_reg = classificar_ancora(t_reg_preco)
        self.assertEqual(cls_reg.category, "REGULAÇÃO")
        self.assertIn("PREÇO", cls_reg.secondary_categories)

        # Colisão entre PESSOAS (prioridade 2) e EXPANSÃO (prioridade 3)
        t_pess_exp = "Empresa abre vagas de emprego para a nova unidade da filial"
        cls_pess = classificar_ancora(t_pess_exp)
        self.assertEqual(cls_pess.category, "PESSOAS")
        self.assertIn("EXPANSÃO", cls_pess.secondary_categories)

    def test_07_comportamento_sem_perfil_de_nicho(self):
        """7. Valida funcionamento autônomo sem necessidade de perfil de nicho configurado."""
        cls = classificar_ancora("Novo aplicativo de entrega lançado no mercado", profile=None)
        self.assertEqual(cls.category, "DIGITAL")
        self.assertTrue(cls.is_known)

    def test_08_comportamento_com_perfil_de_nicho(self):
        """8. Valida enriquecimento declarativo por perfil de nicho sem código específico no core."""
        prof_restaurante = obter_perfil_nicho("restaurante")
        cls_rest = classificar_ancora("Novidades especiais incluídas no cardápio de hoje", profile=prof_restaurante)
        self.assertEqual(cls_rest.category, "PRODUTO/SERVIÇO")

        prof_clinica = obter_perfil_nicho("clinica")
        cls_clin = classificar_ancora("Agendamento de consulta médica por convênio", profile=prof_clinica)
        self.assertTrue(cls_clin.is_known)

    def test_09_determinismo_absoluto(self):
        """9. Valida que execuções repetidas com a mesma entrada produzem exatamente o mesmo resultado."""
        texto = "Inauguração da nova loja com grande campanha e oferta de abertura"
        ref = classificar_ancora(texto)

        for _ in range(50):
            res = classificar_ancora(texto)
            self.assertEqual(res.category, ref.category)
            self.assertEqual(res.confidence, ref.confidence)
            self.assertEqual(res.matched_term, ref.matched_term)
            self.assertEqual(res.secondary_categories, ref.secondary_categories)

    def test_10_compatibilidade_com_consumidores_existentes(self):
        """10. Valida retrocompatibilidade com _primary_event_kind e domain.events."""
        f_reg = Fonte(id=1, titulo="Procon fiscalização no centro", url="https://noticia.com/1", origem="web", conteudo="Multa aplicada por fiscalização")
        kind_reg, dims_reg = _primary_event_kind(f_reg)
        self.assertEqual(kind_reg, "REGULAÇÃO")
        self.assertIn("REGULAÇÃO", dims_reg)

        f_vaga = Fonte(id=2, titulo="Contratação urgente", url="https://vagas.com/2", origem="web", conteudo="50 vagas de emprego abertas para nova unidade")
        kind_vaga, dims_vaga = _primary_event_kind(f_vaga)
        self.assertEqual(kind_vaga, "PESSOAS")
        self.assertIn("PESSOAS", dims_vaga)
        self.assertIn("EXPANSÃO", dims_vaga)

        f_neutra = Fonte(id=3, titulo="Texto comum", url="https://neutro.com/3", origem="web", conteudo="Sem nenhuma âncora aqui")
        kind_neutra, dims_neutra = _primary_event_kind(f_neutra)
        self.assertIsNone(kind_neutra)
        self.assertEqual(dims_neutra, [])

    def test_11_helper_classificar_texto_ancora(self):
        """11. Valida helper rápido de string classificar_texto_ancora."""
        self.assertEqual(classificar_texto_ancora("Desconto e oferta especial"), "PREÇO")
        self.assertEqual(classificar_texto_ancora("Texto sem significado"), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
