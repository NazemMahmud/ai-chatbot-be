"""
Parser Service - Extracts text from documents

Two modes:
1. Simple: pypdf for PDFs, python-docx for Word docs
2. Docling: Heavy-duty parser for scanned docs, images, tables (optional)

Returns structured output with page-level metadata when available.
"""
import io
from pathlib import Path
from typing import NamedTuple

from app.config import settings
from app.enums import DocumentParserType


class ParsedPage(NamedTuple):
    """A single page/section of parsed text with metadata."""
    text: str
    page_number: int | None  # 1-based page number, None if unknown


class ParseResult(NamedTuple):
    """Result of parsing a document."""
    pages: list[ParsedPage]       # page-level text with metadata
    full_text: str                # all text joined (for backward compat)


class ParserService:
    """Document parsing service with multiple backends."""

    def __init__(self, parser_type: DocumentParserType = None):
        self.parser_type = parser_type or DocumentParserType(settings.DEFAULT_PARSER_TYPE)

    async def parse(self, file_content: bytes, mime_type: str, filename: str) -> str:
        """
        Parse document and extract text (backward-compatible).

        Returns:
            Extracted text content as a single string
        """
        result = await self.parse_with_metadata(file_content, mime_type, filename)
        return result.full_text

    async def parse_with_metadata(
        self, file_content: bytes, mime_type: str, filename: str
    ) -> ParseResult:
        """
        Parse document and extract text with page-level metadata.

        Returns:
            ParseResult with pages and full_text
        """
        if self.parser_type == DocumentParserType.DOCLING:
            return await self._parse_with_docling(file_content, mime_type, filename)
        return await self._parse_simple(file_content, mime_type, filename)

    async def _parse_simple(
        self, file_content: bytes, mime_type: str, filename: str
    ) -> ParseResult:
        """Simple parsing using pypdf and python-docx."""
        ext = Path(filename).suffix.lower()

        # PDF — extract per page
        if mime_type == "application/pdf" or ext == ".pdf":
            return await self._parse_pdf(file_content)

        # Word documents
        if mime_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ) or ext in (".docx", ".doc"):
            return await self._parse_docx(file_content)

        # Plain text, markdown, etc.
        if mime_type.startswith("text/") or ext in (".txt", ".md", ".csv", ".html"):
            text = file_content.decode("utf-8", errors="ignore")
            pages = [ParsedPage(text=text, page_number=None)]
            return ParseResult(pages=pages, full_text=text)

        # Images - simple mode can't handle images
        if mime_type.startswith("image/"):
            raise ValueError(
                f"Image files require 'docling' parser mode. Got mime_type={mime_type}"
            )

        # Fallback: try to decode as text
        try:
            text = file_content.decode("utf-8", errors="ignore")
            pages = [ParsedPage(text=text, page_number=None)]
            return ParseResult(pages=pages, full_text=text)
        except Exception:
            raise ValueError(f"Unsupported file type: {mime_type} ({filename})")

    async def _parse_pdf(self, file_content: bytes) -> ParseResult:
        """Parse PDF using pypdf — preserves per-page info."""
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_content))
        pages = []
        text_parts = []

        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append(ParsedPage(text=text, page_number=i + 1))
                text_parts.append(text)

        full_text = "\n\n".join(text_parts)
        return ParseResult(pages=pages, full_text=full_text)

    async def _parse_docx(self, file_content: bytes) -> ParseResult:
        """Parse Word document using python-docx."""
        from docx import Document

        doc = Document(io.BytesIO(file_content))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        full_text = "\n\n".join(paragraphs)

        # Word docs don't have strict page numbers at the parsing level
        pages = [ParsedPage(text=full_text, page_number=None)]
        return ParseResult(pages=pages, full_text=full_text)

    async def _parse_with_docling(
        self, file_content: bytes, mime_type: str, filename: str
    ) -> ParseResult:
        """
        Parse using Docling (handles scanned PDFs, images, complex tables).

        Note: Docling is heavy (~2GB+ dependencies). Only install if needed:
        pip install docling
        """
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            raise ImportError(
                "Docling is not installed. Install with: pip install docling"
            )

        # Write to temp file (docling needs file path)
        import tempfile
        ext = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            full_text = result.document.export_to_markdown()
            # Docling doesn't easily expose per-page text, treat as one block
            pages = [ParsedPage(text=full_text, page_number=None)]
            return ParseResult(pages=pages, full_text=full_text)
        finally:
            import os
            os.unlink(tmp_path)
