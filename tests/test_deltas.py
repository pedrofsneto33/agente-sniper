# -*- coding: utf-8 -*-
"""
Testes Unitários Exclusivos do Módulo domain/deltas.py — Agente Sniper
Cobre: Comparação temporal pura de fontes, fontes novas, alteradas, idênticas,
removidas, sem histórico prévio, listas vazias e caracteres Unicode.
"""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from domain.models import Fonte
from domain.deltas import calcular_delta_fontes
from domain.identity import sha1


class TestDeltas(unittest.TestCase):

    def setUp(self):
        self.f1 = Fonte(
            id=1,
            titulo="Supermercado Carvalho — Notícia 1",
            url="https://carvalho.com.br/noticia1",
            origem="web",
            conteudo="Conteudo original da noticia 1",
            fingerprint="fp_01"
        )
        self.f2 = Fonte(
            id=2,
            titulo="Concorrente Mateus — Vagas",
            url="https://mateus.com.br/vagas",
            origem="web",
            conteudo="Processo seletivo aberto",
            fingerprint="fp_02"
        )

    def test_01_sem_hashes_anteriores_primeira_execucao(self):
        """Testa comportamento quando não há execução anterior (hashes_anteriores=None)."""
        res = calcular_delta_fontes([self.f1, self.f2], hashes_anteriores=None)
        self.assertEqual(res["novas_fontes"], 0)
        self.assertEqual(res["fontes_alteradas"], 0)
        self.assertEqual(res["novos_fingerprints"], set())
        self.assertEqual(res["alterados_fingerprints"], set())

    def test_02_fontes_identicas_zero_deltas(self):
        """Testa fontes com o mesmo fingerprint e mesmo content_hash."""
        old_hashes = {
            "fp_01": sha1(self.f1.conteudo),
            "fp_02": sha1(self.f2.conteudo),
        }
        res = calcular_delta_fontes([self.f1, self.f2], old_hashes)
        self.assertEqual(res["novas_fontes"], 0)
        self.assertEqual(res["fontes_alteradas"], 0)
        self.assertEqual(res["novos_fingerprints"], set())
        self.assertEqual(res["alterados_fingerprints"], set())

    def test_03_nova_fonte_detectada(self):
        """Testa detecção de fonte com fingerprint inédito."""
        old_hashes = {
            "fp_01": sha1(self.f1.conteudo),
        }
        # f2 é nova
        res = calcular_delta_fontes([self.f1, self.f2], old_hashes)
        self.assertEqual(res["novas_fontes"], 1)
        self.assertEqual(res["fontes_alteradas"], 0)
        self.assertIn("fp_02", res["novos_fingerprints"])

    def test_04_fonte_alterada_detectada(self):
        """Testa detecção de fonte com mesmo fingerprint mas conteúdo modificado."""
        f1_modificada = Fonte(
            id=1,
            titulo="Supermercado Carvalho — Notícia 1 Atualizada",
            url="https://carvalho.com.br/noticia1",
            origem="web",
            conteudo="CONTEUDO MODIFICADO E ATUALIZADO",
            fingerprint="fp_01"
        )
        old_hashes = {
            "fp_01": sha1("Conteudo original antigo"),
        }
        res = calcular_delta_fontes([f1_modificada], old_hashes)
        self.assertEqual(res["novas_fontes"], 0)
        self.assertEqual(res["fontes_alteradas"], 1)
        self.assertIn("fp_01", res["alterados_fingerprints"])

    def test_05_fonte_removida_nao_contabilizada(self):
        """Fontes presentes no histórico anterior mas ausentes no lote atual não são deltas."""
        old_hashes = {
            "fp_01": sha1(self.f1.conteudo),
            "fp_removida": sha1("conteudo antigo apagado"),
        }
        res = calcular_delta_fontes([self.f1], old_hashes)
        self.assertEqual(res["novas_fontes"], 0)
        self.assertEqual(res["fontes_alteradas"], 0)

    def test_06_lista_vazia(self):
        """Testa passagem de lista vazia de fontes."""
        old_hashes = {"fp_01": "hash"}
        res = calcular_delta_fontes([], old_hashes)
        self.assertEqual(res["novas_fontes"], 0)
        self.assertEqual(res["fontes_alteradas"], 0)

    def test_07_fontes_duplicadas_no_lote(self):
        """Testa fontes com mesmo fingerprint repetidas no lote atual."""
        f_nova = Fonte(
            id=3, titulo="T", url="u", origem="w",
            conteudo="c", fingerprint="fp_repetido"
        )
        old_hashes = {}
        res = calcular_delta_fontes([f_nova, f_nova], old_hashes)
        self.assertEqual(res["novas_fontes"], 1)
        self.assertEqual(res["fontes_alteradas"], 0)

    def test_08_conteudo_unicode_e_acentos(self):
        """Testa determinismo com caracteres acentuados e caracteres especiais."""
        f_unicode = Fonte(
            id=4,
            titulo="Promoção de Açúcar & Óleo • Teresina — Piauí",
            url="https://carvalho.com.br/promoção",
            origem="web",
            conteudo="Preço com R$ 10,50 & Açúcar Cristal 1kg — São João",
            fingerprint="fp_uni_01"
        )
        old_hashes = {
            "fp_uni_01": sha1("Preço com R$ 10,50 & Açúcar Cristal 1kg — São João")
        }
        res = calcular_delta_fontes([f_unicode], old_hashes)
        self.assertEqual(res["novas_fontes"], 0)
        self.assertEqual(res["fontes_alteradas"], 0)


if __name__ == "__main__":
    unittest.main()
