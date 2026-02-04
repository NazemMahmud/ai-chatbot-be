"""
Sentence-aware text chunking with configurable size and overlap.
"""

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    start_index: int = 0
    end_index: int = 0


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    metadata: dict | None = None,
) -> list[Chunk]:
    """
    Split text into overlapping chunks using sentence-aware splitting.
    chunk_size and chunk_overlap are in word count.
    """
    if not text or not text.strip():
        return []

    # Split by sentences
    sentences = re.split(r"(?<=[.!?])\s+", text)

    chunks = []
    current_chunk: list[str] = []
    current_length = 0
    start_idx = 0

    for sentence in sentences:
        sentence_len = len(sentence.split())

        if current_length + sentence_len > chunk_size and current_chunk:
            # Save current chunk
            chunk_text_str = " ".join(current_chunk)
            chunks.append(
                Chunk(
                    text=chunk_text_str,
                    metadata=metadata or {},
                    start_index=start_idx,
                    end_index=start_idx + len(chunk_text_str),
                )
            )

            # Start new chunk with overlap
            overlap_sentences = []
            overlap_len = 0
            for s in reversed(current_chunk):
                s_len = len(s.split())
                if overlap_len + s_len > chunk_overlap:
                    break
                overlap_sentences.insert(0, s)
                overlap_len += s_len

            current_chunk = overlap_sentences
            current_length = overlap_len
            start_idx = start_idx + len(chunk_text_str) - len(" ".join(current_chunk))

        current_chunk.append(sentence)
        current_length += sentence_len

    # Don't forget last chunk
    if current_chunk:
        chunk_text_str = " ".join(current_chunk)
        chunks.append(
            Chunk(
                text=chunk_text_str,
                metadata=metadata or {},
                start_index=start_idx,
                end_index=start_idx + len(chunk_text_str),
            )
        )

    return chunks
