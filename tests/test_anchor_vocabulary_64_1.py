# -*- coding: utf-8 -*-
import sys, unittest
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from domain.anchors import classificar_ancora

class TestVocabularioCorrigido641(unittest.TestCase):

    def test_01_rs_classifica_preco(self):
        """r$ em texto sem outros termos de preco: categoria PRECO, matched_term=r$."""
        cls = classificar_ancora('empresa cobra r$ 50 por cada item')
        self.assertEqual(cls.category, 'PREÇO')
        self.assertTrue(cls.is_known)
        self.assertEqual(cls.matched_term, 'r$')

    def test_02_funcionario_classifica_pessoas(self):
        """funcionario deve classificar como PESSOAS."""
        cls = classificar_ancora('empresa demite 500 funcionario apos reestruturacao')
        self.assertEqual(cls.category, 'PESSOAS')
        self.assertTrue(cls.is_known)
        self.assertEqual(cls.matched_term, 'funcionario')

    def test_03_produto_classifica_produto_servico(self):
        """produto isolado deve classificar como PRODUTO/SERVICO."""
        cls = classificar_ancora('empresa apresenta novo produto para o mercado regional')
        self.assertEqual(cls.category, 'PRODUTO/SERVIÇO')
        self.assertTrue(cls.is_known)

    def test_04_evento_classifica_marketing(self):
        """evento isolado deve classificar como MARKETING."""
        cls = classificar_ancora('empresa participa de evento setorial em agosto')
        self.assertEqual(cls.category, 'MARKETING')
        self.assertTrue(cls.is_known)
        self.assertEqual(cls.matched_term, 'evento')

    def test_05_precedencia_regulacao_sobre_preco(self):
        """REGULACAO > PRECO por precedencia."""
        cls = classificar_ancora('procon multa empresa que cobrou r$ 200 a mais dos clientes')
        self.assertEqual(cls.category, 'REGULAÇÃO')

    def test_06_precedencia_pessoas_sobre_expansao(self):
        """PESSOAS (prec=2) > EXPANSAO (prec=3) quando ambos presentes."""
        cls = classificar_ancora('empresa inaugura nova unidade e contrata 200 funcionario')
        self.assertEqual(cls.category, 'PESSOAS')
        self.assertIn('EXPANSÃO', cls.secondary_categories)

    def test_07_rs_com_outros_termos_preco_ainda_e_preco(self):
        """r$ junto com desconto: categoria continua PRECO, matched_term eh o mais especifico."""
        cls = classificar_ancora('empresa anuncia r$ 50 de desconto em todos os produtos')
        self.assertEqual(cls.category, 'PREÇO')
        self.assertTrue(cls.is_known)

if __name__ == '__main__':
    unittest.main()
