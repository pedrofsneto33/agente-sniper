# -*- coding: utf-8 -*-
"""
Testes Unitários Exclusivos do Módulo domain/pricing.py — Agente Sniper
Cobre: Cálculo puro de variações de preço, limiar min_change_pct, alternâncias promocionais,
resiliência a valores nulos/zero, limites máximos e múltiplos produtos.
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from domain.pricing import detectar_mudancas_preco


class TestPricing(unittest.TestCase):

    def setUp(self):
        self.snap_base = {
            "entity": "Supermercado Carvalho",
            "source_domain": "carvalho.com.br",
            "product_key": "arroz_1kg",
            "product_name": "Arroz Tio João 1kg",
            "price": 10.00,
            "promotion": 0,
            "url": "https://carvalho.com.br/arroz"
        }

    def test_01_primeira_execucao_sem_historico(self):
        """1. Primeira execução sem snapshot anterior (precos_anteriores=None ou vazio)."""
        res = detectar_mudancas_preco([self.snap_base], precos_anteriores=None)
        self.assertEqual(res, [])
        res_vazio = detectar_mudancas_preco([self.snap_base], precos_anteriores={})
        self.assertEqual(res_vazio, [])

    def test_02_snapshot_anterior_inexistente_para_produto(self):
        """2. Snapshot anterior existe, mas não para o produto observado."""
        old = {("Outro", "outro.com", "feijao_1kg"): (8.00, False)}
        res = detectar_mudancas_preco([self.snap_base], precos_anteriores=old)
        self.assertEqual(res, [])

    def test_03_preco_identico(self):
        """3. Preço idêntico e mesma promoção -> nenhuma mudança."""
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        res = detectar_mudancas_preco([self.snap_base], precos_anteriores=old)
        self.assertEqual(res, [])

    def test_04_aumento_abaixo_do_limiar(self):
        """4. Aumento abaixo do limiar (+0.40% < 0.50%)."""
        snap = dict(self.snap_base, price=10.04)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        res = detectar_mudancas_preco([snap], precos_anteriores=old, min_change_pct=0.5)
        self.assertEqual(res, [])

    def test_05_aumento_exatamente_no_limiar(self):
        """5. Aumento exatamente no limiar (+0.50% == 0.50%)."""
        snap = dict(self.snap_base, price=10.05)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        res = detectar_mudancas_preco([snap], precos_anteriores=old, min_change_pct=0.5)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["change_pct"], 0.50)

    def test_06_aumento_acima_do_limiar(self):
        """6. Aumento acima do limiar (+10.0%)."""
        snap = dict(self.snap_base, price=11.00)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        res = detectar_mudancas_preco([snap], precos_anteriores=old)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["change_pct"], 10.00)
        self.assertEqual(res[0]["previous_price"], 10.00)
        self.assertEqual(res[0]["current_price"], 11.00)

    def test_07_reducao_abaixo_do_limiar(self):
        """7. Redução abaixo do limiar (-0.40%)."""
        snap = dict(self.snap_base, price=9.96)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        res = detectar_mudancas_preco([snap], precos_anteriores=old, min_change_pct=0.5)
        self.assertEqual(res, [])

    def test_08_reducao_exatamente_no_limiar(self):
        """8. Redução exatamente no limiar (-0.50%)."""
        snap = dict(self.snap_base, price=9.95)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        res = detectar_mudancas_preco([snap], precos_anteriores=old, min_change_pct=0.5)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["change_pct"], -0.50)

    def test_09_reducao_acima_do_limiar(self):
        """9. Redução acima do limiar (-15.0%)."""
        snap = dict(self.snap_base, price=8.50)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        res = detectar_mudancas_preco([snap], precos_anteriores=old)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["change_pct"], -15.00)

    def test_10_alteracao_promotion_sem_mudanca_preco(self):
        """10. Alteração de promotion (0 -> 1) com mesmo preço."""
        snap = dict(self.snap_base, price=10.00, promotion=1)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        res = detectar_mudancas_preco([snap], precos_anteriores=old)
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0]["promotion_now"])
        self.assertFalse(res[0]["promotion_before"])
        self.assertEqual(res[0]["change_pct"], 0.0)

    def test_11_alteracao_preco_e_promotion_simultanea(self):
        """11. Alteração de preço e promotion simultâneos."""
        snap = dict(self.snap_base, price=8.00, promotion=1)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        res = detectar_mudancas_preco([snap], precos_anteriores=old)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["change_pct"], -20.00)
        self.assertTrue(res[0]["promotion_now"])
        self.assertFalse(res[0]["promotion_before"])

    def test_12_promotion_igual(self):
        """12. Promotion igual (1 -> 1) sem variação de preço relevante."""
        snap = dict(self.snap_base, price=10.00, promotion=1)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, True)}
        res = detectar_mudancas_preco([snap], precos_anteriores=old)
        self.assertEqual(res, [])

    def test_13_preco_anterior_nulo_ou_zero(self):
        """13. Preço anterior nulo ou zero -> ignora divisão por zero."""
        snap = dict(self.snap_base, price=10.00)
        old_none = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (None, False)}
        old_zero = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (0.0, False)}
        self.assertEqual(detectar_mudancas_preco([snap], precos_anteriores=old_none), [])
        self.assertEqual(detectar_mudancas_preco([snap], precos_anteriores=old_zero), [])

    def test_14_preco_atual_nulo(self):
        """14. Preço atual nulo -> ignora cálculo."""
        snap = dict(self.snap_base, price=None)
        old = {("Supermercado Carvalho", "carvalho.com.br", "arroz_1kg"): (10.00, False)}
        self.assertEqual(detectar_mudancas_preco([snap], precos_anteriores=old), [])

    def test_15_multiplos_produtos_e_entidades(self):
        """15. Múltiplos snapshots com combinação de produtos e concorrentes."""
        snapshots = [
            dict(self.snap_base, product_key="p1", price=12.00), # +20%
            dict(self.snap_base, product_key="p2", price=10.00), # 0%
            dict(self.snap_base, entity="Mateus", product_key="p3", price=8.00, promotion=1), # promo ativada
        ]
        old = {
            ("Supermercado Carvalho", "carvalho.com.br", "p1"): (10.00, False),
            ("Supermercado Carvalho", "carvalho.com.br", "p2"): (10.00, False),
            ("Mateus", "carvalho.com.br", "p3"): (8.00, False),
        }
        res = detectar_mudancas_preco(snapshots, precos_anteriores=old)
        self.assertEqual(len(res), 2)
        keys_changed = {r["product_key"] for r in res}
        self.assertEqual(keys_changed, {"p1", "p3"})

    def test_16_unicode_e_acentuacao(self):
        """16. Identificadores e nomes com caracteres acentuados Unicode."""
        snap = {
            "entity": "Supermercado Carvalho — São Cristóvão",
            "source_domain": "carvalho.com.br",
            "product_key": "açúcar_união_1kg",
            "product_name": "Açúcar União Cristal 1kg • Promoção",
            "price": 5.50,
            "promotion": 0,
            "url": "https://carvalho.com.br/açúcar"
        }
        old = {
            ("Supermercado Carvalho — São Cristóvão", "carvalho.com.br", "açúcar_união_1kg"): (5.00, False)
        }
        res = detectar_mudancas_preco([snap], precos_anteriores=old)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["change_pct"], 10.00)

    def test_17_limite_max_mudancas(self):
        """17. Truncamento estrito em max_mudancas (padrão 100)."""
        snapshots = [
            dict(self.snap_base, product_key=f"p_{i}", price=12.00)
            for i in range(120)
        ]
        old = {
            ("Supermercado Carvalho", "carvalho.com.br", f"p_{i}"): (10.00, False)
            for i in range(120)
        }
        res = detectar_mudancas_preco(snapshots, precos_anteriores=old, max_mudancas=100)
        self.assertEqual(len(res), 100)


if __name__ == "__main__":
    unittest.main()
