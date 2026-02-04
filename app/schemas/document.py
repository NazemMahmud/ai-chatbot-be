import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    mime_type: str | None
    parser_type: str | None
    message: str = "Document accepted for processing"

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: uuid.UUID
    bot_id: uuid.UUID
    name: str
    source_type: str
    source_url: str | None
    mime_type: str | None
    status: str
    error_message: str | None
    chunk_count: int
    parser_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    chunk_count: int
    error_message: str | None

    model_config = {"from_attributes": True}


class URLIngestRequest(BaseModel):
    url: str
    parser_type: str | None = None  # 'simple' or 'docling', null = use env default
