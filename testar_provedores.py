"""
Script de diagnostico para descobrir quais modelos estao funcionando HOJE
"""
import os
from dotenv import load_dotenv
from groq import Groq
from openai import OpenAI

load_dotenv()

CHAVE_GROQ = os.getenv("CHAVE_GROQ")
CHAVE_OPENROUTER = os.getenv("CHAVE_OPENROUTER")
CHAVE_CEREBRAS = os.getenv("CHAVE_CEREBRAS")

print("=" * 70)
print("DIAGNOSTICO DE PROVEDORES DE IA")
print("=" * 70)

# Testar Groq
print("\n[GROQ]")
if CHAVE_GROQ:
    try:
        client = Groq(api_key=CHAVE_GROQ)
        modelos = client.models.list()
        print("  [OK] Conectado ao Groq")
        print("  Modelos disponiveis:")
        for m in modelos.data[:10]:  # Primeiros 10
            print("    - " + m.id)
    except Exception as e:
        print("  [ERRO] " + str(e)[:150])
else:
    print("  [AVISO] Chave nao configurada")

# Testar OpenRouter
print("\n[OPENROUTER]")
if CHAVE_OPENROUTER:
    try:
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=CHAVE_OPENROUTER)
        
        # Testar modelos especificos
        modelos_testar = [
            "openrouter/free",
            "google/gemini-2.0-flash-exp:free",
            "deepseek/deepseek-r1:free",
            "nvidia/nemotron-3-ultra:free",
            "nvidia/nemotron-3.5-lightning:free",
            "qwen/qwen3-235b-a22b:free",
        ]
        
        print("  Testando modelos especificos:")
        for modelo in modelos_testar:
            try:
                response = client.chat.completions.create(
                    model=modelo,
                    messages=[{"role": "user", "content": "Diga apenas: OK"}],
                    max_tokens=10
                )
                print("    [OK] " + modelo)
            except Exception as e:
                print("    [FALHOU] " + modelo + " - " + str(e)[:80])
    except Exception as e:
        print("  [ERRO] " + str(e)[:150])
else:
    print("  [AVISO] Chave nao configurada")

# Testar Cerebras
print("\n[CEREBRAS]")
if CHAVE_CEREBRAS:
    try:
        client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=CHAVE_CEREBRAS)
        
        # Modelos confirmados em Agosto 2026
        modelos_testar = [
            "llama-3.3-70b",
            "llama-4-scout-17b-16e-instruct",
            "qwen-3-32b",
            "deepseek-r1-distill-llama-70b",
        ]
        
        print("  Testando modelos especificos:")
        for modelo in modelos_testar:
            try:
                response = client.chat.completions.create(
                    model=modelo,
                    messages=[{"role": "user", "content": "Diga apenas: OK"}],
                    max_tokens=10
                )
                print("    [OK] " + modelo)
            except Exception as e:
                print("    [FALHOU] " + modelo + " - " + str(e)[:80])
    except Exception as e:
        print("  [ERRO] " + str(e)[:150])
else:
    print("  [AVISO] Chave nao configurada")

print("\n" + "=" * 70)
print("DIAGNOSTICO CONCLUIDO")
print("=" * 70)