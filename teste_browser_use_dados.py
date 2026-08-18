import asyncio
from browser_use import Agent, ChatGoogle


async def main():
    llm = ChatGoogle(model="gemini-3.6-flash")

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
    )

    result = await agent.run()

    print("\n===== RESULTADO =====")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())