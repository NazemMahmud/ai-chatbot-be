"""
Chunker Service - Splits text into chunks for embedding

Two strategies:
  - "character": Recursive character splitting (fast, basic).
  - "semantic":  Embeds sentences, finds topic boundaries by cosine similarity
                 drop, then groups sentences into coherent chunks (slower, smarter).

Factory function `get_chunker()` returns the right one based on settings.
"""
import logging
import math
import re
from typing import List

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy 1: Character splitting (original, fast)
# ---------------------------------------------------------------------------


class CharacterChunkerService:
    """Text chunking using recursive character splitting."""

    SEPARATORS = [
        "\n\n",  # Paragraphs
        "\n",    # Lines
        ". ",    # Sentences
        ", ",    # Clauses
        " ",     # Words
        "",      # Characters (last resort)
    ]

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    def _split_text_recursive(self, text: str, separators: list[str] | None = None) -> list[str]:
        """
        Recursively split text using a hierarchy of separators.

        Tries the first separator that exists in the text. If any resulting
        piece is still too large, falls back to the next separator.
        """
        if separators is None:
            separators = self.SEPARATORS

        final_chunks: list[str] = []

        # Pick the best separator that actually appears in the text
        separator = separators[-1]  # fallback: empty string (char-level)
        remaining_separators = []
        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                remaining_separators = []
                break
            if sep in text:
                separator = sep
                remaining_separators = separators[i + 1 :]
                break

        # Split on the chosen separator
        if separator:
            pieces = text.split(separator)
        else:
            pieces = list(text)  # char-level split

        # Merge small pieces, recurse on large ones
        current_chunk: list[str] = []
        current_length = 0

        for piece in pieces:
            piece_len = len(piece)
            sep_len = len(separator) if separator else 0
            added_len = piece_len + (sep_len if current_chunk else 0)

            if current_length + added_len <= self.chunk_size:
                current_chunk.append(piece)
                current_length += added_len
            else:
                # Flush current chunk
                if current_chunk:
                    merged = separator.join(current_chunk)
                    final_chunks.append(merged)

                    # Keep overlap from the end of the flushed chunk
                    overlap_chunks: list[str] = []
                    overlap_len = 0
                    for prev_piece in reversed(current_chunk):
                        if overlap_len + len(prev_piece) > self.chunk_overlap:
                            break
                        overlap_chunks.insert(0, prev_piece)
                        overlap_len += len(prev_piece) + sep_len

                    current_chunk = overlap_chunks
                    current_length = overlap_len

                # If a single piece exceeds chunk_size, recurse with finer separators
                if piece_len > self.chunk_size and remaining_separators:
                    sub_chunks = self._split_text_recursive(piece, remaining_separators)
                    final_chunks.extend(sub_chunks)
                else:
                    current_chunk.append(piece)
                    current_length += added_len

        # Flush remaining
        if current_chunk:
            merged = separator.join(current_chunk)
            final_chunks.append(merged)

        return [c for c in final_chunks if c.strip()]

    def chunk(self, text: str) -> List[dict]:
        if not text or not text.strip():
            return []

        chunks = self._split_text_recursive(text)

        return [
            {
                "content": chunk,
                "metadata": {
                    "chunk_index": i,
                    "chunk_size": len(chunk),
                    "total_chunks": len(chunks),
                },
            }
            for i, chunk in enumerate(chunks)
        ]

    def chunk_with_sources(self, text: str, source_name: str) -> List[dict]:
        chunks = self.chunk(text)
        for chunk in chunks:
            chunk["metadata"]["source"] = source_name
        return chunks


# ---------------------------------------------------------------------------
# Strategy 2: Semantic splitting (production-grade)
# ---------------------------------------------------------------------------

# Sentence-boundary regex: split after . ! ? followed by whitespace
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")



class SemanticChunkerService:
    """
    Splits text by meaning instead of character count.

    Algorithm:
    1. Split text into sentences
    2. Create sliding windows (3 consecutive sentences each)
    3. Embed each window via the embedding service
    4. Calculate cosine distance between consecutive windows
    5. Find topic breakpoints (bottom X percentile of similarity = biggest jumps)
    6. Group sentences between breakpoints into chunks
    7. Merge small chunks, split oversized ones via character fallback
    """

    def __init__(self, embedding_service):
        self.embedding_service = embedding_service
        self.percentile = settings.SEMANTIC_SIMILARITY_PERCENTILE
        self.min_size = settings.SEMANTIC_MIN_CHUNK_SIZE
        self.max_size = settings.SEMANTIC_MAX_CHUNK_SIZE
        self.max_sentence_chars = settings.SEMANTIC_MAX_SENTENCE_CHARS
        self.max_window_chars = settings.SEMANTIC_MAX_WINDOW_CHARS
        self._char_chunker = CharacterChunkerService(
            chunk_size=self.max_size,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

    # ----- public API -----

    async def chunk_with_sources(self, text: str, source_name: str) -> List[dict]:
        """Main entry point — returns chunks with metadata."""
        if not text or not text.strip():
            return []

        try:
            raw_chunks = await self._semantic_split(text)
        except Exception as e:
            logger.warning(f"Semantic chunking failed ({e}), falling back to character splitter")
            return self._char_chunker.chunk_with_sources(text, source_name)

        # Build metadata
        total = len(raw_chunks)
        result = []
        for i, content in enumerate(raw_chunks):
            result.append({
                "content": content,
                "metadata": {
                    "chunk_index": i,
                    "chunk_size": len(content),
                    "total_chunks": total,
                    "source": source_name,
                    "strategy": "semantic",
                },
            })
        return result

    # ----- core algorithm -----

    async def _semantic_split(self, text: str) -> list[str]:
        """Split text based on embedding similarity between sentence windows."""
        sentences = self._split_sentences(text)
        logger.info(f"[SEMANTIC] Split into {len(sentences)} sentences")

        # Too few sentences — return as a single chunk or fall back
        if len(sentences) <= 5:
            return [text.strip()]

        # Create sliding windows (3 sentences each for stable embeddings)
        windows = self._create_windows(sentences, window_size=3)
        logger.info(f"[SEMANTIC] Created {len(windows)} windows, embedding...")

        # Embed all windows
        window_texts = [w["text"] for w in windows]
        embeddings = await self.embedding_service.embed_batch(window_texts)
        logger.info(f"[SEMANTIC] Embedded {len(embeddings)} windows")

        # Calculate cosine distances between consecutive windows
        distances = []
        for i in range(len(embeddings) - 1):
            dist = 1.0 - self._cosine_similarity(embeddings[i], embeddings[i + 1])
            distances.append(dist)

        # Find breakpoints — bottom X percentile = largest distance = topic shifts
        breakpoints = self._find_breakpoints(distances)
        logger.info(f"[SEMANTIC] Found {len(breakpoints)} topic breakpoints")

        # Group sentences between breakpoints into chunks
        chunks = self._group_sentences(sentences, breakpoints)

        # Post-process: merge too-small, split too-large
        chunks = self._enforce_size_limits(chunks)
        logger.info(f"[SEMANTIC] Final: {len(chunks)} chunks")

        return chunks

    # ----- helpers -----

    def _split_sentences(self, text: str) -> list[str]:
        """
        Split text into sentences using a multi-level strategy:

        1. Paragraph boundaries (\\n\\n or more) — strongest signal
        2. Single newlines (\\n) — list items, headings, code lines
        3. Sentence-ending punctuation (. ! ?) — within a line
        4. Hard length guard — split any sentence still over max_sentence_chars
           at word boundaries so windows never exceed the embedding context.
        """
        max_sentence = self.max_sentence_chars
        raw: list[str] = []

        # Level 1 & 2: paragraph → line split
        for para in re.split(r"\n{2,}", text):
            for line in para.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Level 3: sentence-ending punctuation within the line
                for part in _SENTENCE_RE.split(line):
                    part = part.strip()
                    if part:
                        raw.append(part)

        # Level 4: hard guard — split any sentence over max_sentence_chars
        sentences: list[str] = []
        for s in raw:
            if len(s) <= max_sentence:
                sentences.append(s)
            else:
                # Split at word boundaries to stay under the limit
                words = s.split(" ")
                current = ""
                for word in words:
                    candidate = f"{current} {word}".strip() if current else word
                    if len(candidate) <= max_sentence:
                        current = candidate
                    else:
                        if current:
                            sentences.append(current)
                        current = word
                if current:
                    sentences.append(current)

        return sentences

    def _create_windows(self, sentences: list[str], window_size: int = 3) -> list[dict]:
        """
        Create overlapping sentence windows for embedding.
        Each window = sentence[i] + its neighbors, giving the embedding
        local context instead of a single isolated sentence.

        Safety net: window text is truncated to max_window_chars so the
        embedding model never sees input exceeding its context window,
        even if upstream sentence splitting missed an edge case.
        """
        max_window = self.max_window_chars
        windows = []
        for i in range(len(sentences)):
            start = max(0, i - window_size // 2)
            end = min(len(sentences), i + window_size // 2 + 1)
            window_text = " ".join(sentences[start:end])
            # Safety net: hard truncate at word boundary
            if len(window_text) > max_window:
                window_text = window_text[:max_window].rsplit(" ", 1)[0]
            windows.append({
                "index": i,
                "text": window_text,
            })
        return windows

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors (pure Python)."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _find_breakpoints(self, distances: list[float]) -> list[int]:
        """
        Find indices where cosine distance exceeds the percentile threshold.
        These are topic boundaries — consecutive windows are very different.
        """
        if not distances:
            return []

        # Calculate threshold using percentile (higher distance = less similar)
        sorted_dists = sorted(distances)
        threshold_idx = max(0, int(len(sorted_dists) * (1.0 - self.percentile / 100.0)))
        threshold_idx = min(threshold_idx, len(sorted_dists) - 1)
        threshold = sorted_dists[threshold_idx]

        # Every distance above the threshold is a breakpoint
        breakpoints = []
        for i, dist in enumerate(distances):
            if dist >= threshold:
                breakpoints.append(i + 1)  # +1 because we split AFTER this index

        return breakpoints

    @staticmethod
    def _group_sentences(sentences: list[str], breakpoints: list[int]) -> list[str]:
        """Group sentences between breakpoints into chunk strings."""
        chunks = []
        start = 0
        for bp in sorted(set(breakpoints)):
            if bp <= start:
                continue
            chunk_text = " ".join(sentences[start:bp]).strip()
            if chunk_text:
                chunks.append(chunk_text)
            start = bp

        # Remaining sentences
        if start < len(sentences):
            chunk_text = " ".join(sentences[start:]).strip()
            if chunk_text:
                chunks.append(chunk_text)

        return chunks

    def _enforce_size_limits(self, chunks: list[str]) -> list[str]:
        """Merge chunks that are too small, split chunks that are too large."""
        # Pass 1: merge too-small chunks with their neighbor
        merged = []
        buffer = ""
        for chunk in chunks:
            if buffer:
                combined = buffer + " " + chunk
                if len(combined) <= self.max_size:
                    buffer = combined
                    continue
                else:
                    merged.append(buffer)
                    buffer = chunk
            elif len(chunk) < self.min_size:
                buffer = chunk
            else:
                buffer = chunk

            if len(buffer) >= self.min_size:
                merged.append(buffer)
                buffer = ""

        if buffer:
            if merged:
                # Append to last chunk if possible
                combined = merged[-1] + " " + buffer
                if len(combined) <= self.max_size:
                    merged[-1] = combined
                else:
                    merged.append(buffer)
            else:
                merged.append(buffer)

        # Pass 2: split oversized chunks using character splitter
        final = []
        for chunk in merged:
            if len(chunk) > self.max_size:
                sub_chunks = self._char_chunker.chunk(chunk)
                final.extend([sc["content"] for sc in sub_chunks])
            else:
                final.append(chunk)

        return final


# ---------------------------------------------------------------------------
# Backward compatibility alias
# ---------------------------------------------------------------------------

# Keep ChunkerService as the old name for any existing imports
ChunkerService = CharacterChunkerService
