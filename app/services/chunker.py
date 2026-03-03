"""
Chunker Service - Splits text into chunks for embedding

Custom sentence-aware recursive splitter. No external dependencies.
Supports page-level metadata propagation for citation accuracy.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from app.config import settings

if TYPE_CHECKING:
    from app.services.parser import ParsedPage


class ChunkerService:
    """Text chunking service using recursive character splitting."""

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
        """
        Split text into chunks with metadata.

        Args:
            text: The text to split

        Returns:
            List of dicts with 'content' and 'metadata' keys
        """
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
        """
        Split text and include source information in metadata.

        Args:
            text: The text to split
            source_name: Name of the source document

        Returns:
            List of chunks with source metadata
        """
        chunks = self.chunk(text)
        for chunk in chunks:
            chunk["metadata"]["source"] = source_name
        return chunks

    def chunk_pages(
        self, pages: list["ParsedPage"], source_name: str
    ) -> List[dict]:
        """
        Split page-level text into chunks, preserving page numbers.

        Each chunk knows which page(s) it came from, enabling accurate
        citations like "Source 3, Page 5".

        Args:
            pages: List of ParsedPage(text, page_number)
            source_name: Document name

        Returns:
            List of chunks with page metadata
        """
        if not pages:
            return []

        # Build a list of (char_offset, page_number) markers
        # so we can map any position in the full text back to a page.
        page_markers: list[tuple[int, int | None]] = []
        full_parts: list[str] = []
        offset = 0
        for page in pages:
            if not page.text.strip():
                continue
            page_markers.append((offset, page.page_number))
            full_parts.append(page.text)
            offset += len(page.text) + 2  # +2 for "\n\n" join separator

        full_text = "\n\n".join(full_parts)
        if not full_text.strip():
            return []

        # Split into chunks
        raw_chunks = self._split_text_recursive(full_text)

        # Map each chunk back to page number(s)
        results: list[dict] = []
        search_start = 0

        for i, chunk_text in enumerate(raw_chunks):
            # Find where this chunk starts in the full text
            pos = full_text.find(chunk_text, search_start)
            if pos == -1:
                pos = full_text.find(chunk_text)  # fallback: search from start
            if pos >= 0:
                search_start = pos + 1

            # Determine page number from position
            page_num = None
            if pos >= 0 and page_markers:
                for marker_offset, marker_page in reversed(page_markers):
                    if pos >= marker_offset:
                        page_num = marker_page
                        break

            results.append({
                "content": chunk_text,
                "metadata": {
                    "chunk_index": i,
                    "chunk_size": len(chunk_text),
                    "total_chunks": len(raw_chunks),
                    "source": source_name,
                    "page_number": page_num,
                },
            })

        return results
