"""
Reranker Service - Cross-encoder reranking using FlashRank

After hybrid retrieval (vector + keyword + RRF) returns ~80 candidates,
the reranker scores each candidate against the query with a cross-encoder
model. This is more accurate than embedding similarity because the model
sees the query and passage TOGETHER, not separately.

Uses FlashRank: lightweight, ONNX-based (no PyTorch), ~130MB model.
"""
import logging
import uuid

from app.config import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """Cross-encoder reranker using FlashRank."""

    _ranker = None

    @classmethod
    def _get_ranker(cls):
        """Lazy-load the ranker model (downloads on first use, ~130MB)."""
        if cls._ranker is None:
            try:
                from flashrank import Ranker

                cls._ranker = Ranker(model_name=settings.RERANKER_MODEL)
                logger.info(f"[RERANKER] Loaded model: {settings.RERANKER_MODEL}")
            except ImportError:
                logger.error(
                    "[RERANKER] flashrank not installed. "
                    "Run: pip install flashrank"
                )
                raise
            except Exception as e:
                logger.error(f"[RERANKER] Failed to load model: {e}")
                raise
        return cls._ranker

    @classmethod
    def rerank(
        cls,
        query: str,
        chunk_ids: list[uuid.UUID],
        chunk_contents: list[str],
        top_n: int | None = None,
    ) -> list[uuid.UUID]:
        """
        Rerank chunk candidates using the cross-encoder.

        Args:
            query: The user's search query
            chunk_ids: Ordered list of chunk UUIDs (from RRF merge)
            chunk_contents: Corresponding chunk text contents
            top_n: How many to keep (default: settings.RERANKER_TOP_N)

        Returns:
            Reranked list of chunk UUIDs (most relevant first)
        """
        if top_n is None:
            top_n = settings.RERANKER_TOP_N

        if not chunk_ids or not chunk_contents:
            return chunk_ids

        try:
            from flashrank import RerankRequest

            ranker = cls._get_ranker()

            # Build passages in FlashRank's expected format
            passages = []
            for i, (cid, content) in enumerate(zip(chunk_ids, chunk_contents)):
                passages.append({
                    "id": i,
                    "text": content,
                    "meta": {"chunk_id": str(cid)},
                })

            request = RerankRequest(query=query, passages=passages)
            results = ranker.rerank(request)

            # Results are sorted by relevance score (highest first)
            reranked_ids = []
            for r in results[:top_n]:
                idx = r["id"]
                reranked_ids.append(chunk_ids[idx])

            logger.info(
                f"[RERANKER] Reranked {len(chunk_ids)} → top {len(reranked_ids)} "
                f"(best score: {results[0].get('score', 'N/A') if results else 'N/A'})"
            )
            return reranked_ids

        except ImportError:
            logger.warning("[RERANKER] flashrank not installed, skipping reranking")
            return chunk_ids[:top_n]
        except Exception as e:
            logger.error(f"[RERANKER] Reranking failed: {e}, returning original order")
            return chunk_ids[:top_n]

    @classmethod
    def is_available(cls) -> bool:
        """Check if the reranker can be loaded."""
        try:
            cls._get_ranker()
            return True
        except Exception:
            return False
