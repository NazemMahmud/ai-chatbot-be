import json
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from app.config import settings
from app.enums import DocumentStatus, DocumentParserType, DocumentSourceType, DocumentType


# ---------------------------------------------------------------------------
# Request validation (for multipart/form-data upload)
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "text/markdown",
    "text/html",
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}


class DocumentUploadRequest(BaseModel):
    """
    Validation schema for the document upload form.

    The route extracts metadata from UploadFile + Form fields
    and constructs this model — all validation lives here.
    """
    # --- file (data_file) validation fields ---
    file_name: str = Field(..., description="Original filename from data_file")
    file_content_type: str = Field(..., description="MIME type of data_file")
    file_size: int = Field(..., description="Size of data_file in bytes")

    # --- form fields ---
    bot_ids: list[uuid.UUID] = Field(
        ...,
        description="List of bot IDs to associate the document with (required, at least one)",
    )
    document_type: DocumentType = Field(
        default=DocumentType.GENERAL,
        description="Document type for domain-specific processing (story, ecommerce, law, etc.)",
    )

    # ----- File validators -----

    @field_validator("file_name", mode="before")
    @classmethod
    def validate_file_name(cls, v):
        if not v or not str(v).strip():
            raise PydanticCustomError(
                "missing",
                "A file with a valid filename is required",
            )
        return str(v).strip()

    @field_validator("file_content_type")
    @classmethod
    def validate_file_content_type(cls, v):
        if not v or v not in ALLOWED_MIME_TYPES:
            raise PydanticCustomError(
                "invalid_choice",
                f"File type '{v}' is not supported. "
                "Allowed: pdf, docx, doc, txt, md, html, csv, xls, xlsx, pptx, png, jpg, webp",
            )
        return v

    @field_validator("file_size")
    @classmethod
    def validate_file_size(cls, v):
        if v <= 0:
            raise PydanticCustomError(
                "value_error", "The uploaded file is empty (0 bytes)"
            )
        max_size = getattr(settings, "MAX_FILE_SIZE", None)
        if max_size and v > max_size:
            raise PydanticCustomError(
                "max_length",
                f"File size exceeds the maximum allowed size of {max_size // (1024 * 1024)}MB",
            )
        return v

    # ----- Form field validators -----

    @field_validator("bot_ids", mode="before")
    @classmethod
    def validate_bot_ids(cls, v):
        if v is None or v == "" or v == "null":
            raise PydanticCustomError(
                "required",
                "At least one bot ID is required. Documents must be linked to a bot.",
            )
        # Form field arrives as a JSON string, e.g. '["uuid1","uuid2"]'
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                raise PydanticCustomError(
                    "json_invalid",
                    "Bot ids must be a valid JSON array of UUID strings",
                )
            if not isinstance(parsed, list):
                raise PydanticCustomError(
                    "type_error", "Bot ids must be a JSON array"
                )
            v = parsed
        if isinstance(v, list):
            if len(v) == 0:
                raise PydanticCustomError(
                    "required",
                    "At least one bot ID is required. Documents must be linked to a bot.",
                )
            if len(v) > 20:
                raise PydanticCustomError(
                    "max_length", "Bot ids can contain at most 20 bot IDs"
                )
            result = []
            for item in v:
                try:
                    result.append(uuid.UUID(str(item)))
                except (ValueError, AttributeError):
                    raise PydanticCustomError(
                        "uuid_parsing", f"Invalid UUID in bot ids: {item}"
                    )
            return result
        return v



# ---------------------------------------------------------------------------
# Response data models
# ---------------------------------------------------------------------------

class DocumentUploadData(BaseModel):
    """Data returned after a successful document upload."""
    id: uuid.UUID
    name: str
    status: DocumentStatus
    mime_type: str | None
    parser_type: DocumentParserType | None
    document_type: DocumentType = DocumentType.GENERAL
    bot_ids: list[uuid.UUID] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: uuid.UUID
    bot_ids: list[uuid.UUID] = Field(default_factory=list)
    name: str
    source_type: DocumentSourceType
    source_url: str | None
    mime_type: str | None
    file_size: int | None
    status: DocumentStatus
    error_message: str | None
    chunk_count: int
    parser_type: DocumentParserType | None
    document_type: DocumentType = DocumentType.GENERAL
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentStatusData(BaseModel):
    id: uuid.UUID
    name: str
    status: DocumentStatus
    chunk_count: int
    error_message: str | None
    document_type: DocumentType = DocumentType.GENERAL
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListData(BaseModel):
    documents: list[DocumentResponse]
    total: int


class DocumentUpdateBotsRequest(BaseModel):
    """Request to update the bot associations for a document."""
    bot_ids: list[uuid.UUID] = Field(
        ...,
        description="Complete list of bot IDs to associate (replaces existing associations)",
    )

    @field_validator("bot_ids", mode="before")
    @classmethod
    def validate_bot_ids(cls, v):
        if v is None or not isinstance(v, list):
            raise PydanticCustomError(
                "type_error", "bot_ids must be a list of UUID strings"
            )
        if len(v) == 0:
            raise PydanticCustomError(
                "required",
                "At least one bot ID is required. Documents must be linked to a bot.",
            )
        if len(v) > 20:
            raise PydanticCustomError(
                "max_length", "bot_ids can contain at most 20 bot IDs"
            )
        result = []
        for item in v:
            try:
                result.append(uuid.UUID(str(item)))
            except (ValueError, AttributeError):
                raise PydanticCustomError(
                    "uuid_parsing", f"Invalid UUID in bot_ids: {item}"
                )
        return result


class URLIngestRequest(BaseModel):
    url: str
    bot_ids: list[uuid.UUID] | None = None