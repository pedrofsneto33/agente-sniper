import json
import os
from unittest import mock
import pytest

# Import the functions from llm.client
from llm.client import chamar_deepseek, chamar_llm_json

# Helper to create a mock response object
class MockResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data or {}
        self.status_code = status_code
    def json(self):
        return self._json
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

def test_chamar_deepseek_success(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODELO", "deepseek-chat")
    mock_resp = MockResponse({"choices": [{"message": {"content": "deep result"}}]})
    mock_post = mock.Mock(return_value=mock_resp)
    monkeypatch.setattr("requests.post", mock_post)
    result = chamar_deepseek("test prompt")
    assert result == "deep result"
    args, kwargs = mock_post.call_args
    assert "https://api.deepseek.com/v1/chat/completions" in args[0]
    payload = kwargs.get("json", {})
    assert payload["model"] == "deepseek-chat"
    assert payload["messages"][0]["content"] == "test prompt"

def test_chamar_deepseek_failure(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    mock_post = mock.Mock(side_effect=Exception("network error"))
    monkeypatch.setattr("requests.post", mock_post)
    result = chamar_deepseek("test prompt")
    assert result is None

def test_chamar_llm_json_deepseek_integration(monkeypatch):
    monkeypatch.setattr("llm.client.chamar_ollama", lambda *args, **kwargs: None)
    monkeypatch.setattr("llm.client.chamar_gemini", lambda *args, **kwargs: None)
    monkeypatch.setattr("llm.client.chamar_groq", lambda *args, **kwargs: None)
    json_str = json.dumps({"answer": 42})
    monkeypatch.setattr("llm.client.chamar_deepseek", lambda *args, **kwargs: json_str)
    result = chamar_llm_json("dummy prompt")
    assert isinstance(result, dict)
    assert result["answer"] == 42

def test_fallback_preserves_existing_providers(monkeypatch):
    json_str = json.dumps({"ollama": "ok"})
    monkeypatch.setattr("llm.client.chamar_ollama", lambda *args, **kwargs: json_str)
    result = chamar_llm_json("dummy prompt")
    assert result == {"ollama": "ok"}
