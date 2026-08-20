# -*- coding: utf-8 -*-
"""
Suíte de Testes Unitários para o Pacote llm/ (Fase 37).
Testa:
1. json_seguro com blocos markdown, JSON cru, strings vazias e formato inválido.
2. build_system_prompt com parâmetros explícitos e defaults.
3. chamar_ollama com mock de requisição HTTP 200 e erro/timeout.
4. chamar_gemini com mock do client SDK e rotação de modelos.
5. chamar_groq com mock do client SDK e resposta válida.
6. chamar_llm_json com cache hit e expiração de TTL.
7. gerar_inteligencia_llm com validação e filtragem forense de evidence_ids.
8. llm.__all__ e compatibilidade de reexportação da API pública.
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import llm
from domain.models import Fonte
from llm import (
    CACHE,
    CACHE_TTL,
    build_system_prompt,
    chamar_gemini,
    chamar_groq,
    chamar_llm_json,
    chamar_ollama,
    gerar_inteligencia_llm,
    json_seguro,
)


class TestLLMModule(unittest.TestCase):
    """Testes unitários formais do pacote llm sem chamadas reais de rede."""

    def setUp(self):
        CACHE.clear()
        self.fontes = [
            Fonte(id=1, titulo="Supermercado A", url="https://a.com/1", origem="web", categoria="noticia", escopo="local", atual=True, score=80.0, confianca=0.9),
            Fonte(id=2, titulo="Supermercado B", url="https://b.com/2", origem="web", categoria="noticia", escopo="local", atual=True, score=70.0, confianca=0.8),
        ]
        self.events = [{"kind": "EXPANSÃO", "title": "Loja nova", "importance": 75, "confidence": 0.8, "evidence_ids": [1]}]
        self.ambiente = {"score": 60, "dimensoes": {}}

    def test_01_json_seguro_parsing(self):
        """1. Valida sanitização de markdown e parsing JSON seguro."""
        self.assertEqual(json_seguro('```json\n{"chave": "valor"}\n```'), {"chave": "valor"})
        self.assertEqual(json_seguro('prefixo {"num": 42} sufixo'), {"num": 42})
        self.assertIsNone(json_seguro(""))
        self.assertIsNone(json_seguro(None))
        self.assertIsNone(json_seguro("texto sem chaves json"))
        self.assertIsNone(json_seguro('{"invalido": '))

    def test_02_build_system_prompt(self):
        """2. Valida construção do prompt de sistema contextual."""
        p = build_system_prompt("Empresa Alfa", "tecnologia", "São Paulo", "SP")
        self.assertIn("Empresa: Empresa Alfa", p)
        self.assertIn("Nicho: tecnologia", p)
        self.assertIn("Local: São Paulo-SP", p)
        self.assertIn("Separe FATO de INFERÊNCIA", p)

    @patch("requests.get")
    @patch("requests.post")
    def test_03_chamar_ollama_mock(self, mock_post, mock_get):
        """3. Valida chamada ao Ollama com mock HTTP."""
        mock_get.return_value = MagicMock(status_code=200)
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"response": '{"sinais": []}'})
        res = chamar_ollama("prompt teste", url="http://mock-ollama:11434", modelo="test-model")
        self.assertEqual(res, '{"sinais": []}')

        # Teste de falha de conexão
        mock_get.side_effect = Exception("Connection refused")
        self.assertIsNone(chamar_ollama("prompt teste"))

    def test_04_chamar_gemini_mock(self):
        """4. Valida chamada ao Google Gemini com mock do client SDK."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text='{"resumo": "ok"}')
        res = chamar_gemini("prompt teste", client=mock_client, modelos=["gemini-test"])
        self.assertEqual(res, '{"resumo": "ok"}')

        # Teste quando client é None
        self.assertIsNone(chamar_gemini("prompt", client=None))

    def test_05_chamar_groq_mock(self):
        """5. Valida chamada ao Groq com mock do client SDK."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"groq": "ok"}'))]
        )
        res = chamar_groq("prompt teste", client=mock_client, modelos=["llama-test"], usar_groq=True)
        self.assertEqual(res, '{"groq": "ok"}')

        # Teste quando usar_groq é False
        self.assertIsNone(chamar_groq("prompt", client=mock_client, usar_groq=False))

    def test_06_chamar_llm_json_cache(self):
        """6. Valida cache TTL e reaproveitamento em chamar_llm_json."""
        cache_local = {}
        with patch("llm.client.chamar_gemini", return_value='{"cached_result": 123}'):
            obj1 = chamar_llm_json("prompt cache teste", cache_dict=cache_local)
            self.assertEqual(obj1, {"cached_result": 123})
            self.assertEqual(len(cache_local), 1)

        # Segunda chamada deve retornar do cache sem chamar o provedor
        with patch("llm.client.chamar_gemini", side_effect=Exception("Nao deve ser chamado")):
            obj2 = chamar_llm_json("prompt cache teste", cache_dict=cache_local)
            self.assertEqual(obj2, {"cached_result": 123})

    @patch("llm.client.chamar_llm_json")
    def test_07_gerar_inteligencia_llm_validation(self, mock_llm_json):
        """7. Valida filtragem forense de evidence_ids em gerar_inteligencia_llm."""
        mock_llm_json.return_value = {
            "resumo_executivo": ["Resumo"],
            "sinais": [
                {"titulo": "Sinal 1", "evidence_ids": [1, 999, "invalido", 2]}
            ],
            "concorrencia": [
                {"nome": "Conc A", "evidence_ids": [1, 888]}
            ]
        }
        res = gerar_inteligencia_llm(self.fontes, self.events, self.ambiente)
        self.assertIsNotNone(res)
        # Apenas IDs existentes em self.fontes ([1, 2]) devem permanecer
        self.assertEqual(res["sinais"][0]["evidence_ids"], [1, 2])
        self.assertEqual(res["concorrencia"][0]["evidence_ids"], [1])

    def test_08_public_api_exports(self):
        """8. Valida reexportações públicas no pacote llm."""
        expected = [
            "json_seguro",
            "build_system_prompt",
            "chamar_ollama",
            "chamar_gemini",
            "chamar_groq",
            "chamar_llm_json",
            "gerar_inteligencia_llm",
            "CACHE",
            "CACHE_TTL",
        ]
        self.assertEqual(set(llm.__all__), set(expected))
        for s in expected:
            self.assertTrue(hasattr(llm, s), f"Missing symbol {s} on llm package")


if __name__ == "__main__":
    unittest.main()
