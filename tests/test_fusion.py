# -*- coding: utf-8 -*-
"""
Testes Unitários do Módulo de Fusão de Tokens OCR Fragmentados
"""

import unittest
from extractors.models import BoundingBox, SpatialToken
from extractors.fusion import fundir_tokens_fragmentados


class TestFusion(unittest.TestCase):
    """Testa a reconstrução e fusão determinística de caracteres e sílabas quebradas."""

    def test_01_fusao_caracteres_isolados_horizontal(self):
        """Testa fusão de caracteres soltos (C A F E -> CAFE)."""
        t_c = SpatialToken("C", BoundingBox(10.0, 100.0, 20.0, 130.0), confianca=0.9, id_token=1)
        t_a = SpatialToken("A", BoundingBox(22.0, 100.0, 32.0, 130.0), confianca=0.9, id_token=2)
        t_f = SpatialToken("F", BoundingBox(34.0, 100.0, 44.0, 130.0), confianca=0.9, id_token=3)
        t_e = SpatialToken("E", BoundingBox(46.0, 100.0, 56.0, 130.0), confianca=0.9, id_token=4)

        tokens = [t_c, t_a, t_f, t_e]
        resultado = fundir_tokens_fragmentados(tokens)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].texto, "CAFE")
        self.assertEqual(resultado[0].bbox.x_min, 10.0)
        self.assertEqual(resultado[0].bbox.x_max, 56.0)

    def test_02_fusao_silabas_quebradas(self):
        """Testa fusão de morfemas adjacentes (ALUM + INIO -> ALUMINIO)."""
        t1 = SpatialToken("ALUM", BoundingBox(100.0, 200.0, 180.0, 230.0), confianca=0.95, id_token=1)
        t2 = SpatialToken("INIO", BoundingBox(185.0, 200.0, 250.0, 230.0), confianca=0.95, id_token=2)

        resultado = fundir_tokens_fragmentados([t1, t2])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].texto, "ALUMINIO")

    def test_03_preservacao_palavras_com_espaco_normal(self):
        """Garante que palavras separadas por espaço normal NÃO são fundidas."""
        t1 = SpatialToken("CAFE", BoundingBox(100.0, 200.0, 180.0, 230.0), confianca=0.95, id_token=1)
        # Gap grande de 80px (maior que a altura da fonte de 30px)
        t2 = SpatialToken("PILAO", BoundingBox(260.0, 200.0, 350.0, 230.0), confianca=0.95, id_token=2)

        resultado = fundir_tokens_fragmentados([t1, t2])
        self.assertEqual(len(resultado), 2)
        self.assertEqual(resultado[0].texto, "CAFE")
        self.assertEqual(resultado[1].texto, "PILAO")

    def test_04_fusao_tokens_sem_geometria(self):
        """Testa fusão de caracteres sequenciais em documentos sem BBox."""
        t1 = SpatialToken("P", bbox=None, confianca=0.9, id_token=1)
        t2 = SpatialToken("I", bbox=None, confianca=0.9, id_token=2)
        t3 = SpatialToken("L", bbox=None, confianca=0.9, id_token=3)
        t4 = SpatialToken("A", bbox=None, confianca=0.9, id_token=4)
        t5 = SpatialToken("O", bbox=None, confianca=0.9, id_token=5)

        resultado = fundir_tokens_fragmentados([t1, t2, t3, t4, t5])
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].texto, "PILAO")


if __name__ == "__main__":
    unittest.main()
