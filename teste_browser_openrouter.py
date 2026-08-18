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
    print("=" * 60)
    print("TESTE REAL - BROWSER-USE + OPENROUTER")
    print("=" * 60)

    agent = Agent(
        task="Acesse https://example.com e retorne apenas o título da página.",
        llm=llm,
        use_vision=False,
        max_failures=2,
    )

    print("[AGENT] Executando...")
    resultado = await agent.run(max_steps=5)

    print("")
    print("[RESULTADO]")
    print(resultado)

if __name__ == "__main__":
    asyncio.run(main())
