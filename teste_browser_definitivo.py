import asyncio
import os
from dotenv import load_dotenv
from browser_use import Agent, ChatOpenAI

load_dotenv()

CHAVE = os.getenv("CHAVE_OPENROUTER")

if not CHAVE:
    raise RuntimeError("CHAVE_OPENROUTER nao encontrada no .env")

MODELOS = [
    "openrouter/free",
    "google/gemini-2.0-flash-exp:free",
    "deepseek/deepseek-r1:free",
    "qwen/qwen3-235b-a22b:free",
]

async def testar(modelo):
    print("")
    print("=" * 75)
    print("MODELO:", modelo)
    print("=" * 75)

    try:
        llm = ChatOpenAI(
            model=modelo,
            base_url="https://openrouter.ai/api/v1",
            api_key=CHAVE,
        )

        agent = Agent(
            task=(
                "Acesse https://example.com. "
                "Leia o titulo da pagina. "
                "Quando terminar, responda exatamente: "
                "RESULTADO: Example Domain"
            ),
            llm=llm,
            use_vision=False,
            max_failures=2,
        )

        resultado = await agent.run(max_steps=5)

        texto = str(resultado)

        print("")
        print("[HISTORICO]")
        print(texto[:4000])

        # Verificacao REAL
        sucesso = (
            "Example Domain" in texto
            and "error=" not in texto.lower()
        )

        if sucesso:
            print("")
            print("[CLASSIFICACAO] OK - MODELO FUNCIONOU DE VERDADE")
        else:
            print("")
            print("[CLASSIFICACAO] FALHOU - nao conseguiu completar a tarefa")

    except Exception as e:
        print("")
        print("[CLASSIFICACAO] ERRO")
        print(type(e).__name__ + ": " + str(e)[:1000])


async def main():
    print("=" * 75)
    print("DIAGNOSTICO DEFINITIVO - BROWSER-USE + OPENROUTER")
    print("=" * 75)

    for modelo in MODELOS:
        await testar(modelo)

    print("")
    print("=" * 75)
    print("DIAGNOSTICO FINALIZADO")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(main())
