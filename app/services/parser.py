"""
Parser Service - Extracts text from documents

Two modes:
1. Simple: pypdf for PDFs, python-docx for Word docs
2. Docling: Heavy-duty parser for scanned docs, images, tables (optional)
"""
import io
from pathlib import Path

from app.config import settings
from app.enums import DocumentParserType


class ParserService:
    """Document parsing service with multiple backends."""

    def __init__(self, parser_type: DocumentParserType = None):
        self.parser_type = parser_type or DocumentParserType(settings.DEFAULT_PARSER_TYPE)

    async def parse(self, file_content: bytes, mime_type: str, filename: str) -> str:
        """
        Parse document and extract text.

        Args:
            file_content: Raw file bytes
            mime_type: MIME type of the file
            filename: Original filename (used for extension detection)

        Returns:
            Extracted text content
        """
        if self.parser_type == DocumentParserType.DOCLING:
            return await self._parse_with_docling(file_content, mime_type, filename)
        return await self._parse_simple(file_content, mime_type, filename)

    async def _parse_simple(self, file_content: bytes, mime_type: str, filename: str) -> str:
        """Simple parsing using pypdf and python-docx."""
        ext = Path(filename).suffix.lower()

        # PDF
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
            return file_content.decode("utf-8", errors="ignore")

        # Images - simple mode can't handle images
        if mime_type.startswith("image/"):
            raise ValueError(
                f"Image files require 'docling' parser mode. Got mime_type={mime_type}"
            )

        # Fallback: try to decode as text
        try:
            return file_content.decode("utf-8", errors="ignore")
        except Exception:
            raise ValueError(f"Unsupported file type: {mime_type} ({filename})")

    async def _parse_pdf(self, file_content: bytes) -> str:
        """Parse PDF using pypdf."""
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_content))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n\n".join(text_parts)

    async def _parse_docx(self, file_content: bytes) -> str:
        """Parse Word document using python-docx."""
        from docx import Document

        doc = Document(io.BytesIO(file_content))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n\n".join(paragraphs)

    async def _parse_with_docling(self, file_content: bytes, mime_type: str, filename: str) -> str:
        """
        Parse using Docling (handles scanned PDFs, images, complex tables).

        Note: Docling is heavy (~2GB+ dependencies). Only install if needed:
        pip install docling
        """
        try:
            from docling.document_converter import DocumentConverter
            from docling.datamodel.base_models import InputFormat
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
            return result.document.export_to_markdown()
        finally:
            # Cleanup temp file
            import os
            os.unlink(tmp_path)
