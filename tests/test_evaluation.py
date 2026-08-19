# -*- coding: utf-8 -*-
"""
Testes Unitários do Módulo de Avaliação Quantitativa e Gold Dataset
"""

import unittest
from extractors.models import ExtractedEntity, EvidenceItem, BoundingBox
from extractors.evaluation import GroundTruthItem, avaliar_extracao


class TestEvaluation(unittest.TestCase):
    """Testa o cálculo formal de métricas de acurácia (Precision, Recall, F1, Duplicatas)."""

    def test_01_extracao_perfeita_f1_maximo(self):
        """Testa cenário com 100% de precisão e recall."""
        ent1 = ExtractedEntity(entidade="produto", atributos={"nome": "Cafe"}, valor=15.0, unidade="BRL")
        ent2 = ExtractedEntity(entidade="produto", atributos={"nome": "Cha"}, valor=3.0, unidade="BRL")

        gt1 = GroundTruthItem(entidade="produto", valor=15.0, identificador_item="gt_cafe")
        gt2 = GroundTruthItem(entidade="produto", valor=3.0, identificador_item="gt_cha")

        metricas = avaliar_extracao([ent1, ent2], [gt1, gt2])
        self.assertEqual(metricas.verdadeiros_positivos, 2)
        self.assertEqual(metricas.falsos_positivos, 0)
        self.assertEqual(metricas.falsos_negativos, 0)
        self.assertEqual(metricas.duplicados, 0)
        self.assertEqual(metricas.precision, 1.0)
        self.assertEqual(metricas.recall, 1.0)
        self.assertEqual(metricas.f1_score, 1.0)

    def test_02_deteccao_de_falsos_positivos_e_negativos(self):
        """Testa cenário com 1 falso positivo e 1 falso negativo."""
        # Extraiu valor 99.0 inexistente
        ent1 = ExtractedEntity(entidade="produto", atributos={"nome": "Cafe"}, valor=15.0, unidade="BRL")
        ent_fp = ExtractedEntity(entidade="produto", atributos={"nome": "Fantasma"}, valor=99.0, unidade="BRL")

        gt1 = GroundTruthItem(entidade="produto", valor=15.0, identificador_item="gt_cafe")
        gt_fn = GroundTruthItem(entidade="produto", valor=50.0, identificador_item="gt_nao_extraido")

        metricas = avaliar_extracao([ent1, ent_fp], [gt1, gt_fn])
        self.assertEqual(metricas.verdadeiros_positivos, 1)
        self.assertEqual(metricas.falsos_positivos, 1)
        self.assertEqual(metricas.falsos_negativos, 1)
        self.assertEqual(metricas.precision, 0.5)
        self.assertEqual(metricas.recall, 0.5)
        self.assertEqual(metricas.f1_score, 0.5)

    def test_03_deteccao_de_duplicatas(self):
        """Testa detecção e penalização quando duas entidades disputam o mesmo gabarito."""
        ent1 = ExtractedEntity(entidade="produto", atributos={"nome": "Cafe Original"}, valor=15.0)
        ent_dup = ExtractedEntity(entidade="produto", atributos={"nome": "Cafe Duplicado"}, valor=15.0)

        gt1 = GroundTruthItem(entidade="produto", valor=15.0, identificador_item="gt_cafe")

        metricas = avaliar_extracao([ent1, ent_dup], [gt1])
        self.assertEqual(metricas.verdadeiros_positivos, 1)
        self.assertEqual(metricas.duplicados, 1)
        self.assertEqual(metricas.taxa_duplicacao, 0.5)


if __name__ == "__main__":
    unittest.main()
