from enum import Enum

"""
(str, Enum) => makes the enum JSON-serializable and comparable to strings:

# With (str, Enum):
DocumentStatus.PENDING == "pending"  # True
json.dumps({"status": DocumentStatus.PENDING})  # '{"status": "pending"}'

# Without str:
DocumentStatus.PENDING == "pending"  # False
json.dumps({"status": DocumentStatus.PENDING})  # TypeError

"""

class DocumentSourceType(str, Enum):
    """How the document content was provided."""

    FILE = "file"
    URL = "url"
    TEXT = "text"
    DATABASE = "database"

class DocumentStatus(str, Enum):
    """Processing status of a document."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

class DocumentParserType(str, Enum):
    """Parser mode for document text extraction."""

    SIMPLE = "simple"   # lightweight: pypdf, python-docx
    DOCLING = "docling" # heavy: handles images, tables, OCR