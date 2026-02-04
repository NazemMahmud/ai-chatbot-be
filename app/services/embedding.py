import asyncio

import httpx

from app.config import settings


class EmbeddingService:
    """Supports both Ollama and HuggingFace embedding models."""

    def __init__(self, app_state=None):
        self.provider = settings.EMBED_PROVIDER
        if self.provider == "huggingface" and app_state:
            self.model = app_state.embed_model  # loaded at startup via lifespan

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        if self.provider == "ollama":
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": settings.EMBED_MODEL_NAME, "prompt": text},
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()["embedding"]
        else:
            return self.model.encode(text).tolist()

    async def generate_embeddings(
        self, texts: list[str], batch_size: int = 32
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        if self.provider == "huggingface":
            return self.model.encode(texts, batch_size=batch_size).tolist()
        else:
            # Ollama: batch via asyncio.gather
            embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_results = await asyncio.gather(
                    *[self.generate_embedding(t) for t in batch]
                )
                embeddings.extend(batch_results)
            return embeddings
