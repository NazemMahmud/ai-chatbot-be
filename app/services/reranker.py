"""
Reranker Service - Cross-encoder reranking for RAG pipeline

Uses a lightweight cross-encoder model to re-score (query, chunk) pairs
after initial cosine retrieval. Much more accurate than embedding similarity
alone because it reads query + chunk text together.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (~80MB, runs on CPU)
Speed: ~100-300ms for 50 chunks on CPU
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import DocumentChunk

logger = logging.getLogger(__name__)

# Lazy-loaded singleton to avoid loading the model on every request
_reranker_model = None


def _get_model():
    """Lazy-load the cross-encoder model (singleton)."""
    global _reranker_model
    if _reranker_model is None:
        try:
            from sentence_transformers import CrossEncoder

            _reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("[RERANKER] Cross-encoder model loaded successfully")
        except ImportError:
            logger.warning(
                "[RERANKER] sentence-transformers not installed. "
                "Reranking disabled. Install with: pip install sentence-transformers"
            )
            return None
        except Exception as e:
            logger.error(f"[RERANKER] Failed to load model: {e}")
            return None
    return _reranker_model


def rerank(
    query: str,
    chunks: list["DocumentChunk"],
    top_k: int = 15,
) -> list["DocumentChunk"]:
    """
    Rerank chunks using a cross-encoder model.

    Takes (query, chunk.content) pairs, scores them with the cross-encoder,
    and returns the top_k most relevant chunks sorted by relevance.

    If the cross-encoder is unavailable, falls back to returning
    the original chunks unchanged (cosine-only ordering).

    Args:
        query: The user's question
        chunks: Chunks pre-sorted by cosine similarity
        top_k: Number of top chunks to keep after reranking

    Returns:
        Reranked list of top_k chunks
    """
    if not chunks:
        return []

    if len(chunks) <= top_k:
        # No point reranking if we already have fewer than top_k
        return chunks

    model = _get_model()
    if model is None:
        # Fallback: return top_k from cosine ordering
        logger.info("[RERANKER] Model unavailable, using cosine-only ordering")
        return chunks[:top_k]

    try:
        pairs = [(query, chunk.content) for chunk in chunks]
        scores = model.predict(pairs)

        # Pair chunks with scores, sort by score descending
        scored = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)

        reranked = [chunk for chunk, score in scored[:top_k]]

        logger.info(
            f"[RERANKER] Reranked {len(chunks)} → {len(reranked)} chunks. "
            f"Top score={scored[0][1]:.4f}, cutoff={scored[min(top_k-1, len(scored)-1)][1]:.4f}"
        )

        return reranked

    except Exception as e:
        logger.error(f"[RERANKER] Reranking failed: {e}. Falling back to cosine order.")
        return chunks[:top_k]
