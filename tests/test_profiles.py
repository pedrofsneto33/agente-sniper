# -*- coding: utf-8 -*-
"""
Suíte de Testes Formais para o Catálogo e Resolução de Perfis de Nicho (Fase 35).
Cobre:
1. Exatamente 11 perfis suportados.
2. Presença de todos os 11 identificadores canônicos.
3. Homogeneidade estrutural: cada perfil contém exatamente label, queries, signals.
4. Presença das quantidades esperadas de queries (5 por perfil) e signals (6 a 10 por perfil).
5. Integridade textual dos labels de todos os perfis.
6. Resolução exata individual de cada um dos 11 nichos via obter_perfil_nicho().
7. Resolução case-insensitive.
8. Resolução com remoção de whitespace periférico.
9. Fallback para generico com None, string vazia e apenas espaços.
10. Fallback para generico com nichos desconhecidos.
11. listar_nichos_disponiveis() preserva os 11 nichos na ordem canônica.
12. Retorno do mesmo objeto armazenado (identidade de dicionário e referências).
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.profiles import (
    NICHE_PROFILES,
    obter_perfil_nicho,
    listar_nichos_disponiveis,
)


class TestNicheProfiles(unittest.TestCase):
    """Testes unitários formais para o catálogo e motor de resolução de nichos."""

    EXPECTED_NICHES = [
        "supermercado",
        "restaurante",
        "clinica",
        "hotel",
        "farmacia",
        "imobiliaria",
        "tecnologia",
        "educacao",
        "varejo",
        "servicos",
        "generico",
    ]

    EXPECTED_LABELS = {
        "supermercado": "Varejo alimentar",
        "restaurante": "Alimentação e hospitalidade",
        "clinica": "Saúde e serviços clínicos",
        "hotel": "Hotelaria",
        "farmacia": "Varejo farmacêutico",
        "imobiliaria": "Mercado imobiliário",
        "tecnologia": "Tecnologia e SaaS",
        "educacao": "Educação",
        "varejo": "Varejo geral",
        "servicos": "Serviços",
        "generico": "Empresa genérica",
    }

    def test_01_quantidade_exata_de_perfis(self):
        """1. Valida que o catálogo contém exatamente 11 perfis de nicho."""
        self.assertEqual(len(NICHE_PROFILES), 11)

    def test_02_identificadores_esperados(self):
        """2. Valida que todos os 11 identificadores canônicos estão presentes."""
        self.assertEqual(list(NICHE_PROFILES.keys()), self.EXPECTED_NICHES)

    def test_03_homogeneidade_estrutural(self):
        """3. Valida que cada perfil possui exatamente as chaves 'label', 'queries', 'signals', 'commercial_sources' e 'relevance_weights'."""
        for nicho, prof in NICHE_PROFILES.items():
            with self.subTest(nicho=nicho):
                self.assertIsInstance(prof, dict)
                self.assertEqual(set(prof.keys()), {"label", "queries", "signals", "commercial_sources", "relevance_weights"})
                self.assertIsInstance(prof["label"], str)
                self.assertIsInstance(prof["queries"], list)
                self.assertIsInstance(prof["signals"], list)
                self.assertIsInstance(prof["commercial_sources"], list)
                self.assertIsInstance(prof["relevance_weights"], dict)

    def test_04_quantidades_queries_e_signals(self):
        """4. Valida quantidades esperadas de queries (5) e signals (>= 6)."""
        for nicho, prof in NICHE_PROFILES.items():
            with self.subTest(nicho=nicho):
                self.assertEqual(len(prof["queries"]), 5, f"Perfil {nicho} deve ter 5 queries de busca")
                self.assertGreaterEqual(len(prof["signals"]), 6, f"Perfil {nicho} deve ter ao menos 6 signals")
                for q in prof["queries"]:
                    self.assertIsInstance(q, str)
                    self.assertTrue(len(q.strip()) > 0)
                for s in prof["signals"]:
                    self.assertIsInstance(s, str)
                    self.assertTrue(len(s.strip()) > 0)

    def test_05_labels_textuais_preservados(self):
        """5. Valida que todos os labels correspondem aos valores canônicos."""
        for nicho, expected_label in self.EXPECTED_LABELS.items():
            with self.subTest(nicho=nicho):
                self.assertEqual(NICHE_PROFILES[nicho]["label"], expected_label)

    def test_06_resolucao_individual_dos_11_nichos(self):
        """6. Valida que obter_perfil_nicho retorna o perfil correto para cada uma das 11 chaves."""
        for nicho in self.EXPECTED_NICHES:
            with self.subTest(nicho=nicho):
                prof = obter_perfil_nicho(nicho)
                self.assertEqual(prof["label"], self.EXPECTED_LABELS[nicho])
                self.assertEqual(prof, NICHE_PROFILES[nicho])

    def test_07_resolucao_case_insensitive(self):
        """7. Valida resolução com maiúsculas, minúsculas e mistos."""
        self.assertEqual(obter_perfil_nicho("SUPERMERCADO")["label"], "Varejo alimentar")
        self.assertEqual(obter_perfil_nicho("FaRmAcIa")["label"], "Varejo farmacêutico")
        self.assertEqual(obter_perfil_nicho("TECNOLOGIA")["label"], "Tecnologia e SaaS")

    def test_08_resolucao_com_whitespace(self):
        """8. Valida resolução com espaços em branco no início ou final."""
        self.assertEqual(obter_perfil_nicho("  restaurante  ")["label"], "Alimentação e hospitalidade")
        self.assertEqual(obter_perfil_nicho(" \t clinica \n ")["label"], "Saúde e serviços clínicos")

    def test_09_fallback_para_generico_com_none_ou_vazio(self):
        """9. Valida que None, string vazia ou espaços em branco retornam perfil generico."""
        generico_esperado = NICHE_PROFILES["generico"]
        self.assertEqual(obter_perfil_nicho(None), generico_esperado)
        self.assertEqual(obter_perfil_nicho(""), generico_esperado)
        self.assertEqual(obter_perfil_nicho("   "), generico_esperado)
        self.assertEqual(obter_perfil_nicho(), generico_esperado)

    def test_10_fallback_para_generico_com_nicho_desconhecido(self):
        """10. Valida que nicho desconhecido faz fallback seguro para generico."""
        generico_esperado = NICHE_PROFILES["generico"]
        self.assertEqual(obter_perfil_nicho("mineracao"), generico_esperado)
        self.assertEqual(obter_perfil_nicho("agropecuaria_inexistente"), generico_esperado)
        self.assertEqual(obter_perfil_nicho("12345"), generico_esperado)

    def test_11_listar_nichos_disponiveis(self):
        """11. Valida que listar_nichos_disponiveis retorna os 11 nichos na ordem canônica."""
        nichos = listar_nichos_disponiveis()
        self.assertEqual(nichos, self.EXPECTED_NICHES)
        self.assertEqual(len(nichos), 11)

    def test_12_identidade_de_objeto(self):
        """12. Valida que obter_perfil_nicho retorna a mesma referência de dicionário do catálogo."""
        self.assertIs(obter_perfil_nicho("supermercado"), NICHE_PROFILES["supermercado"])
        self.assertIs(obter_perfil_nicho("generico"), NICHE_PROFILES["generico"])
        self.assertIs(obter_perfil_nicho("desconhecido"), NICHE_PROFILES["generico"])

    def test_13_commercial_sources_declarative_structure(self):
        """13. Valida estrutura declarativa e integridade de commercial_sources por perfil."""
        for nicho, prof in NICHE_PROFILES.items():
            sources = prof["commercial_sources"]
            self.assertIsInstance(sources, list)
            for src in sources:
                self.assertIsInstance(src, dict)
                self.assertIn("name", src)
                self.assertIn("role", src)
                self.assertIn("url", src)
                self.assertIn("channel_type", src)
                self.assertIn(src["role"], {"target", "competitor"})
                self.assertIn(src["channel_type"], {"html_catalog", "flyer_ocr", "interactive_catalog"})
                self.assertTrue(src["url"].startswith("http"))

        # Valida que supermercado possui fontes comerciais auditadas
        self.assertGreater(len(NICHE_PROFILES["supermercado"]["commercial_sources"]), 0)
        # Valida que farmacia e generico mantêm commercial_sources vazio no escopo saneado
        self.assertEqual(len(NICHE_PROFILES["farmacia"]["commercial_sources"]), 0)
        self.assertEqual(len(NICHE_PROFILES["generico"]["commercial_sources"]), 0)


if __name__ == "__main__":
    unittest.main()
