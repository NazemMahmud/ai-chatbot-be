"""
Document parsers — dual mode:
  Mode 1 (simple): lightweight text-only extraction via pypdf, python-docx, etc.
  Mode 2 (docling): comprehensive, handles images/scanned/tables/multilingual.

Parser mode is selectable per-request via API parameter, or defaults to PARSER_TYPE env var.
"""

from app.config import settings


def parse_document(file_path: str, mime_type: str, parser_type: str | None = None) -> str:
    """Parse any document to plain text. Parser selectable via param or env var."""
    use_parser = parser_type or settings.PARSER_TYPE

    if use_parser == "docling":
        return _parse_with_docling(file_path)
    else:
        return _parse_simple(file_path, mime_type)


def _parse_with_docling(file_path: str) -> str:
    """Mode 2: Docling — handles everything (images, tables, OCR, multilingual)."""
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(file_path)
    return result.document.export_to_markdown()


def _parse_simple(file_path: str, mime_type: str) -> str:
    """Mode 1: Simple — lightweight per-format parsers."""
    if mime_type == "application/pdf":
        return _parse_pdf(file_path)
    elif mime_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        return _parse_docx(file_path)
    elif mime_type == "text/html":
        return _parse_html(file_path)
    elif mime_type in ("text/csv", "application/vnd.ms-excel"):
        return _parse_csv(file_path)
    elif mime_type in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ):
        return _parse_xlsx(file_path)
    else:
        return _parse_text(file_path)


def _parse_pdf(file_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _parse_docx(file_path: str) -> str:
    from docx import Document

    doc = Document(file_path)
    return "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])


def _parse_html(file_path: str) -> str:
    from bs4 import BeautifulSoup

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    # Remove script and style elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    return soup.get_text(separator="\n", strip=True)


def _parse_csv(file_path: str) -> str:
    import pandas as pd

    df = pd.read_csv(file_path)
    return df.to_string(index=False)


def _parse_xlsx(file_path: str) -> str:
    import pandas as pd

    df = pd.read_excel(file_path, engine="openpyxl")
    return df.to_string(index=False)


def _parse_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()
