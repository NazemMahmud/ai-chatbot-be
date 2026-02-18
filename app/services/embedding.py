"""
Embedding Service - Generates vector embeddings using Ollama

Uses nomic-embed-text model by default (768 dimensions).
"""
from typing import List

import httpx

from app.config import settings


class EmbeddingService:
    """Embedding service using Ollama."""

    def __init__(
        self,
        model: str = None,
        base_url: str = None,
    ):
        self.model = model or settings.OLLAMA_EMBED_MODEL
        self.base_url = base_url or settings.OLLAMA_BASE_URL

    async def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text,
                },
            )
            response.raise_for_status()
            return response.json()["embedding"]

    async def embed_batch(self, texts: List[str], batch_size: int = 10) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process at once

        Returns:
            List of embedding vectors
        """
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = []
            for text in batch:
                embedding = await self.embed(text)
                batch_embeddings.append(embedding)
            embeddings.extend(batch_embeddings)
        return embeddings

    async def check_health(self) -> bool:
        """Check if Ollama is available and the model is loaded."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Check if Ollama is running
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    return False

                # Check if embedding model is available
                models = response.json().get("models", [])
                model_names = [m["name"].split(":")[0] for m in models]
                return self.model.split(":")[0] in model_names
        except Exception:
            return False
