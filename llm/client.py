# -*- coding: utf-8 -*-
"""
Subsistema de Inteligência Generativa e Provedores LLM — Agente Sniper
Integração estruturada com Ollama local, Google Gemini API e Groq Cloud com fallback resiliente e cache TTL.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from domain.models import Fonte
from domain.identity import sha1
from domain.normalizer import truncar

logger = logging.getLogger("agente_sniper")

# ---------- dependências opcionais de SDKs ----------
try:
    from groq import Groq
except Exception:
    Groq = None

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:
    genai = None
    genai_types = None

# ---------- configuração de provedores ----------
CHAVE_GROQ = os.getenv("CHAVE_GROQ", "").strip()
USAR_GROQ = os.getenv("USAR_GROQ", "0") == "1"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
OLLAMA_MODELO = os.getenv("OLLAMA_MODELO", "gemma3:4b").strip()

GROQ_MODELOS = [
    x.strip() for x in os.getenv(
        "GROQ_MODELOS",
        "llama-3.3-70b-versatile,llama-3.1-70b-versatile,mixtral-8x7b-32768,llama-3.1-8b-instant"
    ).split(",") if x.strip()
]
GEMINI_MODELOS = [
    x.strip() for x in os.getenv(
        "GEMINI_MODELOS",
        "gemini-2.5-flash,gemini-2.0-flash,gemini-1.5-flash"
    ).split(",") if x.strip()
]

# DeepSeek configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODELO = os.getenv("DEEPSEEK_MODELO", "deepseek-chat").strip()


# ---------- clientes inicializados ----------
client_groq = None
client_gemini = None
if CHAVE_GROQ and Groq:
    try:
        client_groq = Groq(api_key=CHAVE_GROQ)
    except Exception:
        pass
if GEMINI_API_KEY and genai:
    try:
        client_gemini = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass

CACHE: Dict[str, Tuple[str, float]] = {}
CACHE_TTL = 21600


def json_seguro(texto: str) -> Optional[Dict[str, Any]]:
    """Sanitiza blocos de código markdown e extrai payload JSON estruturado."""
    if not texto:
        return None
    s = str(texto).strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except Exception:
        return None


def build_system_prompt(
    empresa_alvo: Optional[str] = None,
    nicho: Optional[str] = None,
    cidade: Optional[str] = None,
    estado: Optional[str] = None,
) -> str:
    """Monta a instrução de sistema contextual para o analista LLM."""
    empresa = empresa_alvo or os.getenv("EMPRESA_ALVO", "Supermercado Carvalho")
    n = nicho or os.getenv("NICHO", "supermercado")
    cid = cidade or os.getenv("CIDADE", "Teresina")
    est = estado or os.getenv("ESTADO", "PI")

    return f"""
Você é o motor de inteligência competitiva do Agente Sniper.
Empresa: {empresa}
Nicho: {n}
Local: {cid}-{est}

Você recebe evidências previamente coletadas. Não navegue, não invente fatos.
Separe FATO de INFERÊNCIA ESTRATÉGICA. Nunca trate ausência de evidência como ausência.
Toda afirmação factual precisa indicar evidence_ids. Não invente IDs.
Seu trabalho é responder: o que mudou, por que importa, qual risco existe,
qual oportunidade existe e que decisão deveria ser considerada.
""".strip()


def chamar_ollama(
    prompt: str,
    system_prompt: Optional[str] = None,
    url: Optional[str] = None,
    modelo: Optional[str] = None,
) -> Optional[str]:
    """Chama a API local do Ollama para geração de JSON."""
    ollama_url = (url or OLLAMA_URL).rstrip("/")
    ollama_mod = modelo or OLLAMA_MODELO
    sys_p = system_prompt or build_system_prompt()
    try:
        r = requests.get(f"{ollama_url}/api/tags", timeout=4)
        if r.status_code >= 400:
            return None
        r = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": ollama_mod, "prompt": f"{sys_p}\n\n{prompt}", "stream": False, "format": "json"},
            timeout=180,
        )
        r.raise_for_status()
        return str(r.json().get("response", "")).strip() or None
    except Exception:
        return None


def chamar_gemini(
    prompt: str,
    system_prompt: Optional[str] = None,
    modelos: Optional[List[str]] = None,
    client: Any = None,
) -> Optional[str]:
    """Chama a API do Google Gemini com rotação de modelos."""
    cli = client or client_gemini
    if not cli or not genai_types:
        return None
    sys_p = system_prompt or build_system_prompt()
    mods = modelos or GEMINI_MODELOS
    for model in mods:
        try:
            cfg = genai_types.GenerateContentConfig(system_instruction=sys_p, max_output_tokens=5000)
            r = cli.models.generate_content(model=model, contents=prompt, config=cfg)
            txt = (getattr(r, "text", "") or "").strip()
            if txt:
                return txt
        except Exception as e:
            logger.warning("[GEMINI] %s: %s", model, str(e)[:120])
    return None


def chamar_groq(
    prompt: str,
    system_prompt: Optional[str] = None,
    modelos: Optional[List[str]] = None,
    client: Any = None,
    usar_groq: Optional[bool] = None,
) -> Optional[str]:
    """Chama a API da Groq Cloud com rotação de modelos e suporte a JSON mode."""
    habilitado = USAR_GROQ if usar_groq is None else usar_groq
    cli = client or client_groq
    if not habilitado or not cli:
        return None
    sys_p = system_prompt or build_system_prompt()
    mods = modelos or GROQ_MODELOS
    for model in mods:
        try:
            kwargs: Dict[str, Any] = {
                "model": model,
                "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 5000,
            }
            if os.getenv("GROQ_JSON_MODE", "1") == "1":
                kwargs["response_format"] = {"type": "json_object"}
            r = cli.chat.completions.create(**kwargs)
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                return txt
        except Exception as e:
            logger.warning("[GROQ] %s: %s", model, str(e)[:120])
    return None


def chamar_deepseek(prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
    """Call DeepSeek API (OpenAI compatible) and return response text."""
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    messages = [{"role": "user", "content": prompt}]
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})
    payload = {"model": DEEPSEEK_MODELO, "messages": messages}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        txt = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return txt or None
    except Exception as e:
        logger.warning("[DEEPSEEK] %s: %s", DEEPSEEK_MODELO, str(e)[:120])
        return None

def chamar_llm_json(
    prompt: str,
    system_prompt: Optional[str] = None,
    cache_dict: Optional[Dict[str, Tuple[str, float]]] = None,
) -> Optional[Dict[str, Any]]:
    """Dispatcher sequencial com fallback e cache TTL."""
    sys_p = system_prompt or build_system_prompt()
    cache = {} if cache_dict is None else cache_dict
    key = sha1(sys_p + prompt)
    cached = cache.get(key)

    if cached and time.time() - cached[1] < CACHE_TTL:
        return json_seguro(cached[0])

    fornecedores = []
    if os.getenv("USAR_OLLAMA", "1") == "1":
        fornecedores.append(("ollama", lambda p: chamar_ollama(p, system_prompt=sys_p)))
    fornecedores.append(("gemini", lambda p: chamar_gemini(p, system_prompt=sys_p)))
    if USAR_GROQ:
        fornecedores.append(("groq", lambda p: chamar_groq(p, system_prompt=sys_p)))
    fornecedores.append(("deepseek", lambda p: chamar_deepseek(p, system_prompt=sys_p)))

    for nome, fn in fornecedores:
        try:
            result = fn(prompt)
            obj = json_seguro(result or "")
            if obj:
                cache[key] = (result or "", time.time())
                logger.info("[IA] %s respondeu JSON", nome)
                return obj
        except Exception as e:
            logger.warning("[IA] %s falhou: %s", nome, str(e)[:140])
    return None


def gerar_inteligencia_llm(
    fontes: List[Fonte],
    events: List[Dict[str, Any]],
    ambiente: Dict[str, Any],
    empresa_alvo: Optional[str] = None,
    nicho: Optional[str] = None,
    cidade: Optional[str] = None,
    estado: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Constrói o prompt executivo, consulta os provedores LLM e valida os evidence_ids.
    """
    empresa = empresa_alvo or os.getenv("EMPRESA_ALVO", "Supermercado Carvalho")
    n = nicho or os.getenv("NICHO", "supermercado")
    cid = cidade or os.getenv("CIDADE", "Teresina")
    est = estado or os.getenv("ESTADO", "PI")
    sys_p = build_system_prompt(empresa, n, cid, est)

    evidencias = []
    for f in sorted(fontes, key=lambda x: x.score, reverse=True)[:36]:
        evidencias.append({
            "id": f.id,
            "titulo": truncar(f.titulo, 180),
            "url": f.url,
            "categoria": f.categoria,
            "data": f.data_publicacao,
            "atual": f.atual,
            "escopo": f.escopo,
            "score": round(f.score, 1),
            "confianca": round(f.confianca, 2),
            "trecho": truncar(f.resumo_busca or f.conteudo, 650),
        })

    prompt = f"""
RETORNE SOMENTE JSON VÁLIDO. Você é o estrategista de inteligência competitiva do Agente Sniper.
Empresa: {empresa}
Nicho: {n}
Local: {cid}-{est}

OBJETIVO:
Transformar fatos públicos em decisões úteis. Não invente fatos.
Uma ação estratégica pode ser uma inferência, mas deve estar claramente apoiada por evidence_ids.
Nunca trate uma única reclamação como problema estrutural.
Nunca use uma fonte sem data como se fosse evidência recente.
Nunca conte a mesma fonte como várias evidências independentes.
Não trate diretório/catálogo como prova de desempenho, preço real ou crescimento.
Não use fonte corporativa para afirmar desempenho local sem evidência local.
Não invente concorrentes: use apenas concorrentes configurados ou explicitamente identificados nas evidências. Um evento da própria empresa não pode ser descrito como movimento de um concorrente.

SCHEMA:
{{
  "resumo_executivo": ["..."],
  "sinais": [
    {{"titulo":"...","tipo":"RISCO|OPORTUNIDADE|MOVIMENTO","impacto":"BAIXO|MEDIO|ALTO","urgencia":"BAIXA|MEDIA|ALTA","racional":"...","acao":"...","evidence_ids":[1],"confianca":0.0,"limite":"..."}}
  ],
  "concorrencia": [
    {{"nome":"...","movimento":"...","confianca":0.0,"evidence_ids":[1]}}
  ],
  "prioridades_30": ["..."],
  "prioridades_60": ["..."],
  "prioridades_90": ["..."],
  "lacunas": ["..."]
}}

ÍNDICES PRELIMINARES:
- atividade da empresa: ambiente_competitivo.score
- pressão competitiva externa: pressao_competitiva.score (pode ser nulo)
- vulnerabilidade da empresa: vulnerabilidade_empresa.score
- momentum do mercado: momentum_mercado

{json.dumps(ambiente, ensure_ascii=False)}

EVENTOS CANÔNICOS:
Cada event_id representa um fato. Não crie eventos adicionais a partir das mesmas evidências.
{json.dumps(events[:36], ensure_ascii=False)}

EVIDÊNCIAS:
{json.dumps(evidencias, ensure_ascii=False)}
"""
    obj = chamar_llm_json(prompt, system_prompt=sys_p)
    if not obj:
        return None
    ids_validos = {f.id for f in fontes}
    for item in obj.get("sinais", []) or []:
        if isinstance(item, dict):
            item["evidence_ids"] = [int(x) for x in item.get("evidence_ids", []) if str(x).isdigit() and int(x) in ids_validos]
    for item in obj.get("concorrencia", []) or []:
        if isinstance(item, dict):
            item["evidence_ids"] = [int(x) for x in item.get("evidence_ids", []) if str(x).isdigit() and int(x) in ids_validos]
    return obj
