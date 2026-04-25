"""
Chunking configuration registry mapping document types to chunking parameters.
"""

CHUNKING_CONFIGS = {
    "general": {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    "story": {
        "chunk_size": 1500,
        "chunk_overlap": 300,
        "separators": ["\n\n\n", "\n\n", "\n", ". ", " ", ""],
    },
    "ecommerce": {
        "chunk_size": 500,
        "chunk_overlap": 50,
        "separators": ["\n\n\n", "\n\n", "\n", ". ", " ", ""],
    },
    "business": {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    "law": {
        "chunk_size": 800,
        "chunk_overlap": 250,
        "separators": ["\n\n\n", "\n\n", "\n", "; ", ". ", " ", ""],
    },
    "finance": {
        "chunk_size": 800,
        "chunk_overlap": 200,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    "medical": {
        "chunk_size": 800,
        "chunk_overlap": 250,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    "technical": {
        "chunk_size": 1200,
        "chunk_overlap": 200,
        "separators": ["\n\n\n", "\n\n", "\n", ". ", " ", ""],
    },
    "education": {
        "chunk_size": 1000,
        "chunk_overlap": 250,
        "separators": ["\n\n", "\n", ". ", ", ", " ", ""],
    },
    "support": {
        "chunk_size": 600,
        "chunk_overlap": 100,
        "separators": ["\n\n\n", "\n\n", "? ", ". ", "\n", " ", ""],
    },
}


def get_chunking_config(document_type: str) -> dict:
    """Get chunking configuration for a document type, with fallback to general."""
    return CHUNKING_CONFIGS.get(document_type, CHUNKING_CONFIGS["general"])
