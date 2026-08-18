"""Diagnostico 2: Descobrir como criar o LLM corretamente"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()
chave_or = os.getenv("CHAVE_OPENROUTER")
chave_groq = os.getenv("CHAVE_GROQ")

print("=" * 60)
print("DIAGNOSTICO 2 - ESTRUTURA DO BROWSER-USE")
print("=" * 60)

# TESTE 1: Ver o que tem dentro do browser_use
print("")
print("[TESTE 1] Conteudo do modulo browser_use...")
try:
    import browser_use
    conteudo = dir(browser_use)
    print("  Itens disponiveis:")
    for item in conteudo:
        if not item.startswith('_'):
            print("    - " + item)
except Exception as e:
    print("  ERRO: " + str(e))

# TESTE 2: Verificar se existe browser_use.llm
print("")
print("[TESTE 2] Verificando browser_use.llm...")
try:
    from browser_use import llm
    print("  OK: browser_use.llm existe")
    print("  Conteudo: " + str(dir(llm)))
except ImportError:
    print("  NAO existe browser_use.llm")
except Exception as e:
    print("  ERRO: " + str(e))

# TESTE 3: Verificar se existe ChatOpenAI dentro do browser_use
print("")
print("[TESTE 3] Verificando ChatOpenAI no browser_use...")
try:
    from browser_use import ChatOpenAI as BrowserChatOpenAI
    print("  OK: browser_use.ChatOpenAI existe!")
except ImportError:
    print("  NAO existe browser_use.ChatOpenAI")
except Exception as e:
    print("  ERRO: " + str(e))

# TESTE 4: Verificar parametros do Agent
print("")
print("[TESTE 4] Parametros aceitos pelo Agent...")
try:
    from browser_use import Agent
    import inspect
    sig = inspect.signature(Agent.__init__)
    print("  Parametros: " + str(sig))
except Exception as e:
    print("  ERRO: " + str(e))

# TESTE 5: Tentar ChatOpenAI com provider manual
print("")
print("[TESTE 5] ChatOpenAI com provider='openai'...")
try:
    from langchain_openai import ChatOpenAI
    from browser_use import Agent
    llm = ChatOpenAI(
        model="openrouter/free",
        base_url="https://openrouter.ai/api/v1",
        api_key=chave_or,
    )
    llm.provider = "openai"
    agent = Agent(task="Diga ola", llm=llm)
    print("  OK: Agent criado com provider manual!")
except Exception as e:
    print("  FALHOU: " + type(e).__name__ + ": " + str(e)[:150])

# TESTE 6: Tentar com ChatGroq
print("")
print("[TESTE 6] Tentando ChatGroq...")
try:
    from langchain_groq import ChatGroq
    from browser_use import Agent
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=chave_groq,
    )
    agent = Agent(task="Diga ola", llm=llm)
    print("  OK: Agent criado com ChatGroq!")
except ImportError:
    print("  langchain_groq nao instalado")
    print("  Instale com: py -3.13 -m pip install langchain-groq")
except Exception as e:
    print("  FALHOU: " + type(e).__name__ + ": " + str(e)[:150])

# TESTE 7: Tentar criar Agent sem llm (para ver erro)
print("")
print("[TESTE 7] Agent sem llm (para ver mensagem de erro)...")
try:
    from browser_use import Agent
    agent = Agent(task="Diga ola")
    print("  OK: Agent criado sem llm!")
except Exception as e:
    print("  ERRO (esperado): " + type(e).__name__ + ": " + str(e)[:200])

# TESTE 8: Versao do browser-use
print("")
print("[TESTE 8] Versao do browser-use...")
try:
    import importlib.metadata
    versao = importlib.metadata.version('browser-use')
    print("  Versao: " + versao)
except Exception:
    try:
        import browser_use
        print("  Versao: " + str(getattr(browser_use, '__version__', 'desconhecida')))
    except Exception:
        print("  Nao foi possivel determinar")

print("")
print("=" * 60)
print("DIAGNOSTICO 2 CONCLUIDO")
print("=" * 60)