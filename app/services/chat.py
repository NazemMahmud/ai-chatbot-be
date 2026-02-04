"""
Chat/LLM service — handles streaming responses from Ollama chat models.
"""

from collections.abc import AsyncGenerator

import httpx

from app.config import settings


class ChatService:
    async def generate_response(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from Ollama chat API."""
        model = model or settings.CHAT_MODEL_NAME
        temperature = temperature if temperature is not None else settings.CHAT_TEMPERATURE

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": temperature},
                },
                timeout=120.0,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        import orjson

                        data = orjson.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
                        if data.get("done", False):
                            break
