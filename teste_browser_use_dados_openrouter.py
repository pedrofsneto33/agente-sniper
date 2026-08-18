import asyncio
import os
from dotenv import load_dotenv
from browser_use import Agent, ChatOpenAI

load_dotenv()

chave = os.getenv("CHAVE_OPENROUTER")

if not chave:
    raise RuntimeError("CHAVE_OPENROUTER não encontrada no .env")

llm = ChatOpenAI(
    model="openrouter/free",
    base_url="https://openrouter.ai/api/v1",
    api_key=chave,
)

async def main():
    agent = Agent(
        task="""
        Abra o Google.
        Pesquise por: "cotação dólar hoje".

        Leia os resultados da pesquisa.

        Retorne SOMENTE um JSON válido neste formato:

        {
          "consulta": "cotação dólar hoje",
          "titulo_primeiro_resultado": "...",
          "dominio_primeiro_resultado": "...",
          "url_primeiro_resultado": "..."
        }

        Não faça nenhuma outra ação.
        """,
        llm=llm,
        use_vision=False,
        max_failures=2,
    )

    result = await agent.run(max_steps=6)

    print("\n===== RESULTADO =====")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())