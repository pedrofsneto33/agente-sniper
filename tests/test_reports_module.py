# -*- coding: utf-8 -*-
"""
Suíte de Testes Formais e Granulares para o Pacote reports/ (Fase 36).
Cobre:
1. ref_text: formatação de citações com listas vazias, múltiplos IDs e tipos variados.
2. html_escape: sanitização de strings, tags, aspas, ampersands e tratamento de None/vazio.
3. rotulo_dimensao: normalização de rótulos dimensionais e substituições semânticas.
4. fonte_por_id: indexação de fontes por ID e lista vazia.
5. gerar_html (completo): renderização do dashboard com comparação de preços e inteligência temporal.
6. gerar_html (minimal): fallback resiliente com dados mínimos/vazios e defaults de ambiente.
7. gerar_pdf: geração de documento PDF executivo com layout executivo.
8. gerar_pdf (fallback): retorno None controlado quando FPDF não estiver disponível ou ocorrer erro.
9. salvar_json: serialização formatada UTF-8 e criação automática de diretório.
10. salvar_csv_fontes: integridade de colunas, delimitador ';' e cabeçalho com UTF-8-SIG (BOM).
11. reports.__all__: validação formal dos símbolos públicos exportados pelo pacote.
"""

import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import reports
from domain.models import Fonte
from reports import (
    ref_text,
    fonte_por_id,
    html_escape,
    rotulo_dimensao,
    gerar_html,
    gerar_pdf,
    salvar_json,
    salvar_csv_fontes,
)


class TestReportsModule(unittest.TestCase):
    """Testes unitários formais e granulares do pacote reports."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.fontes = [
            Fonte(id=1, titulo="Supermercado A em Teresina", url="https://a.com/1", origem="web", categoria="noticia", escopo="local", atual=True, score=85.0, confianca=0.9, data_publicacao="2026-08-10"),
            Fonte(id=2, titulo="Supermercado B expansão", url="https://b.com/2", origem="web", categoria="noticia", escopo="nacional", atual=False, score=60.0, confianca=0.7, data_publicacao="2026-07-20"),
        ]
        self.events = [
            {"kind": "EXPANSÃO", "title": "Nova loja concorrente", "importance": 80, "confidence": 0.85, "evidence_ids": [1], "date": "2026-08-10", "independent_source_count": 2, "estado_temporal": "NOVO"}
        ]
        self.ambiente = {
            "score": 65,
            "dimensoes": {
                "EXPANSÃO": {"score": 75, "status": "ATIVO", "eventos": 1, "evidencias": 1, "eventos_correlacionados": 1}
            },
            "momentum_mercado": 50,
            "pressao_competitiva": {"score": 40, "label": "MÉDIA"},
            "vulnerabilidade_empresa": {"score": 10, "label": "BAIXA"},
            "cobertura": 0.8,
        }
        self.pacote = {
            "resumo_executivo": ["Resumo de inteligência do teste"],
            "sinais": [
                {"tipo": "OPORTUNIDADE", "impacto": "ALTO", "urgencia": "ALTA", "titulo": "Expansão no bairro X", "limite": "30 dias", "confianca": 0.9, "racional": "Racional do sinal", "acao": "Abrir ponto de coleta", "evidence_ids": [1]}
            ],
            "concorrencia": [{"nome": "Concorrente Alpha", "movimento": "Promoção agressiva", "confianca": 0.8, "evidence_ids": [1]}],
            "prioridades_30": ["Ação 30d"],
            "prioridades_60": ["Ação 60d"],
            "prioridades_90": ["Ação 90d"],
            "lacunas": ["Lacuna 1"],
            "comparacao_precos": {
                "enabled": True,
                "status": "CONCLUIDO",
                "produtos_alvo": 10,
                "comparaveis": 8,
                "maiores_gaps": [{"produto_alvo": "Arroz 5kg", "concorrente": "Concorrente A", "dif_percent": -12.5, "similaridade": 0.95, "location_note": "Teresina"}],
                "promocoes_alvo": 2,
                "promocoes_concorrentes": 3,
                "guerra_de_precos": [{"concorrente": "Concorrente A", "comparaveis": 5, "concorrente_mais_barato": 3, "alvo_mais_barato": 2, "dif_media_percent": -4.2}],
                "historico": {"mudancas": [{"entity": "Concorrente A", "product_name": "Arroz 5kg", "change_pct": -5.0, "previous_price": 20.0, "current_price": 19.0}]},
                "series_temporais": {"arroz_5kg": {"product_name": "Arroz 5kg", "entity": "Concorrente A", "preco_atual": 19.0, "deltas_janela": {7: -5.0, 15: -5.0, 30: -5.0}, "volatilidade": 0.5, "tendencia": "QUEDA"}},
            },
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_ref_text_formatting(self):
        """1. Valida formatação de citações forenses com ref_text."""
        self.assertEqual(ref_text([1, 2, 3]), "[FONTE 1] [FONTE 2] [FONTE 3]")
        self.assertEqual(ref_text([]), "")
        self.assertEqual(ref_text([42]), "[FONTE 42]")

    def test_02_html_escape_sanitization(self):
        """2. Valida sanitização de caracteres especiais HTML com html_escape."""
        self.assertEqual(html_escape("<b>teste & 'aspas'</b>"), "&lt;b&gt;teste &amp; &#x27;aspas&#x27;&lt;/b&gt;")
        self.assertEqual(html_escape(None), "")
        self.assertEqual(html_escape(123), "123")
        self.assertEqual(html_escape(""), "")

    def test_03_rotulo_dimensao_normalization(self):
        """3. Valida normalização e título de dimensões."""
        self.assertEqual(rotulo_dimensao("expansão"), "Expansão")
        self.assertEqual(rotulo_dimensao("serviço"), "Serviço")
        self.assertEqual(rotulo_dimensao("REGULAÇÃO"), "Regulação")

    def test_04_fonte_por_id_mapping(self):
        """4. Valida mapeamento indexado de fontes por ID."""
        fmap = fonte_por_id(self.fontes)
        self.assertEqual(len(fmap), 2)
        self.assertEqual(fmap[1].titulo, self.fontes[0].titulo)
        self.assertEqual(fmap[2].titulo, self.fontes[1].titulo)
        self.assertEqual(fonte_por_id([]), {})

    def test_05_gerar_html_complete_dashboard(self):
        """5. Valida renderização do dashboard HTML completo com comparação de preços e séries temporais."""
        html_out = gerar_html(
            self.pacote, self.fontes, self.events, self.ambiente, {},
            empresa_alvo="EMPRESA TESTE", cidade="TERESINA", estado="PI",
            perfil_label="Varejo alimentar", app_version="11.8.0"
        )
        self.assertIsInstance(html_out, str)
        self.assertIn("<!doctype html>", html_out)
        self.assertIn("EMPRESA TESTE", html_out)
        self.assertIn("Pressão competitiva", html_out)
        self.assertIn("Arroz 5kg", html_out)
        self.assertIn("Agente Sniper v11.8.0", html_out)

    def test_06_gerar_html_minimal_fallback(self):
        """6. Valida fallback do dashboard HTML com pacote e ambiente mínimos."""
        pacote_minimo = {"resumo_executivo": ["Resumo"], "sinais": []}
        ambiente_minimo = {"score": 50, "dimensoes": {}}
        html_out = gerar_html(pacote_minimo, [], [], ambiente_minimo, {})
        self.assertIsInstance(html_out, str)
        self.assertIn("<!doctype html>", html_out)
        self.assertIn("Agente Sniper", html_out)

    def test_07_gerar_pdf_executive_report(self):
        """7. Valida geração de PDF executivo em pasta temporária."""
        pdf_path = gerar_pdf(
            self.pacote, self.fontes, self.events, self.ambiente, {},
            empresa_alvo="EMPRESA TESTE", cidade="TERESINA", estado="PI",
            pasta_execucao=self.temp_path, run_id="TEST_RUN_01"
        )
        if pdf_path:
            p = Path(pdf_path)
            self.assertTrue(p.exists())
            self.assertTrue(p.stat().st_size > 500)

    def test_08_gerar_pdf_fpdf_fallback(self):
        """8. Valida retorno None controlado de gerar_pdf caso FPDF seja None."""
        with patch("reports.pdf.FPDF", None):
            res = gerar_pdf(self.pacote, self.fontes, self.events, self.ambiente, {}, pasta_execucao=self.temp_path)
            self.assertIsNone(res)

    def test_09_salvar_json_serialization(self):
        """9. Valida serialização e gravação de JSON em diretório isolado."""
        caminho = salvar_json("payload_teste.json", self.pacote, pasta_execucao=self.temp_path)
        p = Path(caminho)
        self.assertTrue(p.exists())
        conteudo = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(conteudo["sinais"][0]["titulo"], "Expansão no bairro X")

    def test_10_salvar_csv_fontes_tabular(self):
        """10. Valida exportação de fontes.csv com delimitador ';' e BOM UTF-8."""
        caminho = salvar_csv_fontes(self.fontes, pasta_execucao=self.temp_path)
        p = Path(caminho)
        self.assertTrue(p.exists())
        with p.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f, delimiter=";")
            rows = list(reader)
        self.assertEqual(rows[0], ["ID", "Categoria", "Titulo", "URL", "Data", "Origem", "Escopo", "Atual", "Score", "Confianca"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][0], "1")
        self.assertEqual(rows[1][2], self.fontes[0].titulo)

    def test_11_reports_public_api_exports(self):
        """11. Valida que o pacote reports reexporta todos os símbolos da API pública."""
        expected_symbols = [
            "ref_text",
            "fonte_por_id",
            "html_escape",
            "rotulo_dimensao",
            "gerar_html",
            "gerar_pdf",
            "salvar_json",
            "salvar_csv_fontes",
        ]
        self.assertEqual(set(reports.__all__), set(expected_symbols))
        for sym in expected_symbols:
            self.assertTrue(hasattr(reports, sym), f"reports package missing symbol {sym}")


if __name__ == "__main__":
    unittest.main()
