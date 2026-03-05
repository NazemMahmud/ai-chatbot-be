"""
Embedding Service - Generates vector embeddings using Ollama

Default model: nomic-embed-text (8192 token context, optimized for RAG).

Each text is embedded via an individual /api/embed request. Requests run
concurrently (asyncio.gather + semaphore) over a shared HTTP client so
throughput is high without any batch-context-length issues.

Defensive measures:
  - _prepare_text(): normalise whitespace and hard-truncate to EMBED_MAX_INPUT_CHARS
  - shrink-retry: if Ollama returns a context-length error, halve the text and
    retry up to EMBED_SHRINK_RETRIES times.
"""
import asyncio
import logging
import re
from typing import List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding service using Ollama."""

    def __init__(self, model: str = None, base_url: str = None):
        self.model = model or settings.OLLAMA_EMBED_MODEL
        self.base_url = base_url or settings.OLLAMA_BASE_URL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        async with httpx.AsyncClient(timeout=settings.EMBED_TIMEOUT) as client:
            return await self._embed_one(client, text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts concurrently.

        Each text is sent as an individual /api/embed request so there is
        no combined-context-length issue regardless of text size or count.
        A shared AsyncClient and asyncio.Semaphore provide connection reuse
        and back-pressure (EMBED_MAX_CONCURRENT requests in flight at once).

        Empty/whitespace texts are replaced with zero vectors so index
        alignment with the input list is always preserved.
        """
        if not texts:
            return []

        # Identify empty texts — replaced with zero vectors at the end
        empty_indices: set[int] = {
            i for i, t in enumerate(texts) if not t or not t.strip()
        }
        if empty_indices:
            logger.warning(f"embed_batch: {len(empty_indices)} empty text(s) skipped")

        non_empty = [(i, t) for i, t in enumerate(texts) if i not in empty_indices]

        if not non_empty:
            raise ValueError("All texts are empty — nothing to embed")

        max_concurrent = settings.EMBED_MAX_CONCURRENT
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _bounded(idx: int, text: str) -> tuple[int, List[float]]:
            async with semaphore:
                return idx, await self._embed_one(client, text)

        logger.info(
            f"embed_batch: {len(non_empty)} texts, "
            f"concurrent={max_concurrent}"
        )

        async with httpx.AsyncClient(timeout=settings.EMBED_TIMEOUT) as client:
            results: List[tuple[int, List[float]]] = await asyncio.gather(
                *[_bounded(i, t) for i, t in non_empty]
            )

        # asyncio.gather preserves submission order, but sort by original index
        # to be explicit and safe
        results.sort(key=lambda x: x[0])
        embeddings_by_idx = dict(results)

        # Reconstruct output list; fill empties with zero vectors
        dim = len(next(iter(embeddings_by_idx.values())))
        zero_vec = [0.0] * dim

        return [
            embeddings_by_idx.get(i, zero_vec) for i in range(len(texts))
        ]

    async def check_health(self) -> bool:
        """Check if Ollama is available and the embedding model is loaded."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    return False
                models = response.json().get("models", [])
                model_names = [m["name"].split(":")[0] for m in models]
                return self.model.split(":")[0] in model_names
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_text(text: str) -> str:
        """
        Normalise and truncate text before sending to the embedding model.

        1. Collapse runs of whitespace (including newlines) into single spaces.
        2. Strip leading/trailing whitespace.
        3. Hard-truncate at EMBED_MAX_INPUT_CHARS on a word boundary.
        """
        max_chars = settings.EMBED_MAX_INPUT_CHARS
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_chars:
            text = text[:max_chars].rsplit(" ", 1)[0]
        return text

    @staticmethod
    def _is_context_error(response: httpx.Response) -> bool:
        """Return True if the 400 is specifically a context-length overflow."""
        if response.status_code != 400:
            return False
        body = response.text.lower()
        return "context length" in body or "too long" in body or "exceeds" in body

    async def _embed_one(
        self, client: httpx.AsyncClient, text: str
    ) -> List[float]:
        """
        Embed a single text with defensive preparation and shrink-retry.

        Steps:
        1. Prepare (normalise + truncate) the input text.
        2. POST to Ollama /api/embed.
        3. If context-length error → halve text and retry (up to N times).
        4. Any other error → raise immediately.
        """
        text = self._prepare_text(text)
        max_retries = settings.EMBED_SHRINK_RETRIES
        min_chars = settings.EMBED_MIN_RETRY_CHARS

        for attempt in range(max_retries + 1):
            response = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": text},
            )

            if response.status_code == 200:
                return response.json()["embeddings"][0]

            if self._is_context_error(response) and attempt < max_retries:
                new_len = max(len(text) // 2, min_chars)
                if new_len < min_chars:
                    break
                logger.warning(
                    f"Context overflow (attempt {attempt + 1}), "
                    f"shrinking {len(text)} → {new_len} chars"
                )
                text = text[:new_len].rsplit(" ", 1)[0]
                continue

            # Non-context error or exhausted retries
            logger.error(
                f"Ollama /api/embed failed: status={response.status_code}, "
                f"body={response.text[:300]}"
            )
            response.raise_for_status()

        # Should not reach here, but just in case
        raise RuntimeError(f"Embedding failed after {max_retries} shrink retries")
