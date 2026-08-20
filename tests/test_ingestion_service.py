"""
Testes Unitários do Módulo pipeline.ingestion (Fase 44).
Validação dos contratos de orquestração de busca concorrente, enriquecimento web,
atualização transparente de _IO_STATS e identidade de bindings com o monólito.
"""

import unittest
from unittest.mock import MagicMock, patch

from domain.models import Fonte
from pipeline.ingestion import coletar_tudo, enriquecer
import agente_sniper_v11_8 as sniper


class TestIngestionService(unittest.TestCase):

    def test_01_coletar_tudo_com_io_stats_telemetry(self):
        """1. Valida que coletar_tudo preenche discovery_tasks e discovery_time no dicionário io_stats."""
        stats = {"discovery_tasks": 0, "discovery_time": 0.0}
        mock_results = [{"title": "Item 1", "url": "https://exemplo.com/1"}]

        with patch("pipeline.ingestion._search_coletar_tudo", return_value=mock_results) as mock_search:
            consultas_dummy = {"empresa": [("consulta 1", "alvo")]}
            res = coletar_tudo(
                tavily_client=None,
                consultas=consultas_dummy,
                max_consultas_por_grupo=1,
                usar_tavily=False,
                usar_ddg=True,
                usar_news_rss=True,
                io_stats=stats
            )
            self.assertEqual(res, mock_results)
            self.assertEqual(stats["discovery_tasks"], 2)  # 1 ddg + 1 news_rss
            self.assertGreater(stats["discovery_time"], 0.0)

    def test_02_enriquecer_com_io_stats_telemetry(self):
        """2. Valida que enriquecer preenche enrich_tasks e enrich_time no dicionário io_stats."""
        stats = {"enrich_tasks": 0, "enrich_time": 0.0}
        f1 = Fonte(id=1, titulo="T1", url="https://exemplo.com/1", origem="Web", score=10.0)
        f2 = Fonte(id=2, titulo="T2", url="https://exemplo.com/2", origem="Web", score=5.0)
        fontes = [f1, f2]

        with patch("pipeline.ingestion._web_enriquecer", return_value=fontes) as mock_enrich:
            res = enriquecer(fontes, max_enriquecimento=5, io_stats=stats)
            self.assertEqual(res, fontes)
            self.assertEqual(stats["enrich_tasks"], 2)
            self.assertGreater(stats["enrich_time"], 0.0)

    def test_03_binding_identity_with_orchestrator(self):
        """3. Valida que os símbolos em agente_sniper_v11_8 são identicamente ligados a pipeline.ingestion."""
        self.assertIs(sniper.coletar_tudo, coletar_tudo)
        self.assertIs(sniper.enriquecer, enriquecer)


if __name__ == "__main__":
    unittest.main()
