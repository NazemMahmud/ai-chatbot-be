"""
Chunking configuration registry mapping document types to chunking parameters.
"""
from app.enums import DocumentType

CHUNKING_CONFIGS = {
    DocumentType.GENERAL: {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    DocumentType.STORY: {
        "chunk_size": 1500,
        "chunk_overlap": 300,
        "separators": ["\n\n\n", "\n\n", "\n", ". ", " ", ""],
    },
    DocumentType.ECOMMERCE: {
        "chunk_size": 500,
        "chunk_overlap": 50,
        "separators": ["\n\n\n", "\n\n", "\n", ". ", " ", ""],
    },
    DocumentType.BUSINESS: {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    DocumentType.LAW: {
        "chunk_size": 800,
        "chunk_overlap": 250,
        "separators": ["\n\n\n", "\n\n", "\n", "; ", ". ", " ", ""],
    },
    DocumentType.FINANCE: {
        "chunk_size": 800,
        "chunk_overlap": 200,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    DocumentType.MEDICAL: {
        "chunk_size": 800,
        "chunk_overlap": 250,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    DocumentType.TECHNICAL: {
        "chunk_size": 1200,
        "chunk_overlap": 200,
        "separators": ["\n\n\n", "\n\n", "\n", ". ", " ", ""],
    },
    DocumentType.EDUCATION: {
        "chunk_size": 1000,
        "chunk_overlap": 250,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    DocumentType.SUPPORT: {
        "chunk_size": 600,
        "chunk_overlap": 100,
        "separators": ["\n\n\n", "\n\n", "? ", ". ", "\n", " ", ""],
    },
}


def get_chunking_config(document_type: str | DocumentType) -> dict:
    """Get chunking configuration for a document type, with fallback to general."""
    # Convert string to enum if necessary
    if isinstance(document_type, str):
        try:
            document_type = DocumentType(document_type)
        except ValueError:
            document_type = DocumentType.GENERAL

    return CHUNKING_CONFIGS.get(document_type, CHUNKING_CONFIGS[DocumentType.GENERAL])
