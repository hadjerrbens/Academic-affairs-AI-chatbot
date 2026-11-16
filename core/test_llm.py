import asyncio
from llm import GroqClient, TokenBudget

async def main():
    budget = TokenBudget(limit=5000)
    client = GroqClient(budget=budget)

    messages = [
        {
            "role": "user",
            "content": "Explain what a computer network is in 3 short sentences."
        }
    ]
    async for chunk in client.stream(messages):
        print(chunk, end="", flush=True)


asyncio.run(main())