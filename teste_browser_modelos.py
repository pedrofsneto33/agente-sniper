import asyncio
import os
from dotenv import load_dotenv
from browser_use import Agent, ChatOpenAI

load_dotenv()

chave = os.getenv("CHAVE_OPENROUTER")

MODELOS = [
    "z-ai/glm-5.2:free",
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
]


async def testar(modelo):
    print("")
    print("=" * 70)
    print("TESTANDO:", modelo)
    print("=" * 70)

    try:
        llm = ChatOpenAI(
            model=modelo,
            base_url="https://openrouter.ai/api/v1",
            api_key=chave,
        )

        agent = Agent(
            task="""
Acesse https://example.com.

Extraia:
1. o título da página;
2. o texto principal da página.

Retorne SOMENTE:

{
  "titulo": "...",
  "texto": "..."
}

Não faça nenhuma outra ação.
""",
            llm=llm,
            use_vision=False,
            max_failures=2,
        )

        resultado = await agent.run(max_steps=5)

        print("")
        print("[RESULTADO]")
        print(resultado)

        # Compatibilidade com diferentes versões do browser-use
        if hasattr(resultado, "final_result"):
            final = resultado.final_result()
        else:
            final = str(resultado)

        print("")
        print("[FINAL]")
        print(final)

        # Verificação real
        texto = str(final)

        if "Example Domain" in texto:
            print("")
            print("[STATUS] MODELO FUNCIONOU")
            return True
        else:
            print("")
            print("[STATUS] MODELO NAO ENTREGOU O RESULTADO ESPERADO")
            return False

    except Exception as e:
        print("")
        print("[STATUS] MODELO FALHOU")
        print(type(e).__name__ + ": " + str(e)[:1000])
        return False


async def main():
    if not chave:
        raise RuntimeError(
            "CHAVE_OPENROUTER nao encontrada no .env"
        )

    resultados = {}

    for modelo in MODELOS:
        resultados[modelo] = await testar(modelo)

    print("")
    print("=" * 70)
    print("RESUMO FINAL")
    print("=" * 70)

    for modelo, funcionou in resultados.items():
        status = "OK" if funcionou else "FALHOU"
        print(f"{status:8} {modelo}")


if __name__ == "__main__":
    asyncio.run(main())