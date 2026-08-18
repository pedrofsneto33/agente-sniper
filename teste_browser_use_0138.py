import asyncio
import os

from browser_use import Agent, ChatGoogle


async def main():
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY não está configurada.")

    llm = ChatGoogle(
        model="gemini-3.6-flash",
        api_key=api_key,
    )

    agent = Agent(
        task="Abra o Google e pesquise por 'browser-use'. Não faça mais nada.",
        llm=llm,
    )

    result = await agent.run()

    print("\n===== RESULTADO =====")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())