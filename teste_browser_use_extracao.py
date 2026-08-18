import asyncio
from browser_use import Agent, ChatGoogle


async def main():
    agent = Agent(
        task="""
        Abra o Google.
        Pesquise por "Python".
        Leia os resultados da pesquisa.
        Retorne somente:
        1. O título do primeiro resultado.
        2. O domínio/site do primeiro resultado.
        Não faça nenhuma outra ação.
        """,
        llm=ChatGoogle(model="gemini-3.6-flash"),
    )

    result = await agent.run()

    print("\n===== RESULTADO =====")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())