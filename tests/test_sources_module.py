"""
Testes Unitários do Módulo domain.sources (Fase 40).
Garante validação isolada, determinismo e ausência de I/O / rede / browser / SQLite.
"""

import unittest
from unittest.mock import patch

from domain.models import Fonte
from domain.sources import (
    DOMINIOS_PRIORITARIOS,
    CIDADES_EXTERIORES,
    dominios_oficiais_configurados,
    score_fonte,
    classificar_escopo,
    sinais_deterministicos,
    transformar,
    deduplicar,
)
import agente_sniper_v11_8 as sniper


class TestSourcesModule(unittest.TestCase):

    def test_01_dominios_oficiais_configurados(self):
        """1. Valida derivação de domínios oficiais configurados a partir de envs e JSON."""
        with patch.dict("os.environ", {
            "EMPRESA_URL": "https://www.carvalho.com.br",
            "PRECO_ALVO_URLS": "https://loja.carvalho.com.br|https://app.carvalho.com.br",
            "PRICE_SOURCES_JSON": '[{"url": "https://concorrente1.com.br/busca"}, {"search_url": "https://concorrente2.com.br/busca"}]',
        }):
            doms = dominios_oficiais_configurados()
            self.assertIn("carvalho.com.br", doms)
            self.assertIn("concorrente1.com.br", doms)
            self.assertIn("concorrente2.com.br", doms)

    def test_02_sinais_deterministicos_taxonomy(self):
        """2. Valida categorização taxonômica determinística de sinais textuais."""
        texto = "Supermercado anuncia promoção de produtos frescos com desconto imperdível e nova loja em Teresina"
        sinais = sinais_deterministicos(texto)
        self.assertIn("preço", sinais)
        self.assertIn("expansão", sinais)
        self.assertIn("produto", sinais)

        texto_vazio = ""
        self.assertEqual(sinais_deterministicos(texto_vazio), [])

    def test_03_classificar_escopo_geografico(self):
        """3. Valida classificação determinística de escopo territorial."""
        # Local (Teresina no PI)
        escopo, c, e = classificar_escopo("Inauguração de nova filial em Teresina no PI", corporativo=False)
        self.assertEqual(escopo, "local")
        self.assertTrue(c)
        self.assertTrue(e)

        # Nacional (PI sem Teresina)
        escopo, c, e = classificar_escopo("Comércio e varejo no PI em alta", corporativo=False)
        self.assertEqual(escopo, "nacional")
        self.assertFalse(c)
        self.assertTrue(e)

        # Global (Cidade exterior sem localidade)
        escopo, c, e = classificar_escopo("Conferência de varejo internacional em New York e Miami", corporativo=False)
        self.assertEqual(escopo, "global")
        self.assertFalse(c)
        self.assertFalse(e)

        # Corporativo
        escopo, c, e = classificar_escopo("Relatório de governança e resultados", corporativo=True)
        self.assertEqual(escopo, "corporativo")

        # Incerto
        escopo, c, e = classificar_escopo("Notícia geral sem localidade", corporativo=False)
        self.assertEqual(escopo, "incerto")

    def test_04_score_fonte_calculation(self):
        """4. Valida cálculo matemático e ponderação exata de score_fonte."""
        f = Fonte(
            id=1,
            titulo="Carvalho Supermercado Abre Filial",
            url="https://g1.globo.com/pi/noticia-1",
            resumo_busca="Resumo da notícia",
            origem="web",
            score=0.0,
            alias_empresa="Carvalho",
            cidade_confirmada=True,
            atual=True,
            data_publicacao="2026-08-01",
            direta=True,
            conteudo="A" * 1200,
            escopo="local",
            dominio="g1.globo.com",
            sinais=["preço", "expansão"],
        )
        sc = score_fonte(f)
        # 34 (alias) + 18 (cidade) + 18 (atual) + 7 (direta) + 5 (len>=1000) + 6 (escopo local) + (8 * 0.92 = 7.36) + (2*2 = 4)
        expected = 34 + 18 + 18 + 7 + 5 + 6 + (8 * 0.92) + 4
        self.assertAlmostEqual(sc, expected, places=2)

    def test_05_transformar_raw_to_fonte(self):
        """5. Valida transformação completa de raw dictionary em instância Fonte com score e fingerprint."""
        raw = {
            "titulo": "Supermercado Carvalho inaugura loja moderna em Teresina",
            "url": "https://portalodia.com/noticias/carvalho-loja",
            "conteudo": "O Supermercado Carvalho inaugurou hoje mais uma grande unidade com foco em preços baixos e produtos de qualidade.",
            "origem": "tavily",
            "categoria": "noticias",
            "data": "2026-08-20",
        }
        f = transformar(raw, 1)
        self.assertIsNotNone(f)
        self.assertEqual(f.id, 1)
        self.assertEqual(f.alias_empresa.lower(), "supermercado carvalho")
        self.assertTrue(f.cidade_confirmada)
        self.assertEqual(f.escopo, "local")
        self.assertTrue(f.score > 50.0)
        self.assertTrue(len(f.fingerprint) == 40)

    def test_06_transformar_rejection_criteria(self):
        """6. Valida rejeições determinísticas de transformar() em casos inválidos ou homônimos."""
        # URL vazia
        self.assertIsNone(transformar({"url": "", "titulo": "Teste"}, 1))

        # Homônimo conflitante
        with patch.dict("os.environ", {"TERMOS_CONFLITANTES_IDENTIDADE": "madeireira,pisos,vigas"}):
            raw_conflito = {
                "url": "https://madeireira.com/carvalho",
                "titulo": "Madeireira Carvalho - Venda de Pisos e Vigas de Madeira",
                "conteudo": "Madeiras nobres e acabamentos em Carvalho para construção civil.",
            }
            self.assertIsNone(transformar(raw_conflito, 2))

        # Data anterior ao limite histórico
        raw_antigo = {
            "url": "https://noticias.com/antiga",
            "titulo": "Supermercado Carvalho em Teresina",
            "conteudo": "Notícia muito antiga do Supermercado Carvalho em Teresina",
            "data_publicacao": "2015-05-10",
        }
        self.assertIsNone(transformar(raw_antigo, 3))

    def test_07_deduplicar_deterministic_priority(self):
        """7. Valida deduplicação estável preservando fontes de maior score e renumerando IDs."""
        f1 = Fonte(id=10, titulo="Fonte A", url="https://site.com/a", resumo_busca="", origem="web", score=90.0, fingerprint="fp1")
        f2 = Fonte(id=20, titulo="Fonte A Duplicada", url="https://site.com/a", resumo_busca="", origem="web", score=60.0, fingerprint="fp2")
        f3 = Fonte(id=30, titulo="Fonte B", url="https://site.com/b", resumo_busca="", origem="web", score=80.0, fingerprint="fp3")

        dedup = deduplicar([f2, f1, f3])
        self.assertEqual(len(dedup), 2)
        self.assertEqual(dedup[0].url, "https://site.com/a")
        self.assertEqual(dedup[0].score, 90.0)
        self.assertEqual(dedup[0].id, 1)
        self.assertEqual(dedup[1].url, "https://site.com/b")
        self.assertEqual(dedup[1].id, 2)

    def test_08_public_contracts_compatibility(self):
        """8. Valida compatibilidade programática entre o monólito e o módulo domain.sources."""
        symbols = [
            "dominios_oficiais_configurados",
            "score_fonte",
            "classificar_escopo",
            "sinais_deterministicos",
            "transformar",
            "deduplicar",
        ]
        import domain.sources as ds
        for s in symbols:
            self.assertTrue(hasattr(sniper, s), f"Missing {s} in orchestrator")
            self.assertTrue(hasattr(ds, s), f"Missing {s} in domain.sources")
            self.assertTrue(callable(getattr(sniper, s)))
            self.assertTrue(callable(getattr(ds, s)))


if __name__ == "__main__":
    unittest.main()
