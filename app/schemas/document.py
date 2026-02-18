import json
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.enums import DocumentStatus, DocumentParserType, DocumentSourceType


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

IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


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
    bot_ids: Optional[list[uuid.UUID]] = Field(
        None,
        description="List of bot IDs to associate the document with (optional)",
    )
    parser_type: DocumentParserType = Field(
        ...,
        description="Parser type: 'simple' or 'docling'. Required.",
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
        if v > MAX_FILE_SIZE:
            raise PydanticCustomError(
                "max_length",
                f"File size exceeds the maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB",
            )
        return v

    # ----- Form field validators -----

    @field_validator("bot_ids", mode="before")
    @classmethod
    def validate_bot_ids(cls, v):
        if v is None or v == "" or v == "null":
            return None
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

    @field_validator("parser_type", mode="before")
    @classmethod
    def validate_parser_type(cls, v):
        if v is None or v == "" or v == "null":
            raise PydanticCustomError(
                "required",
                "Parser type is required. Must be 'simple' or 'docling'",
            )
        if isinstance(v, str):
            v = v.strip().lower()
        # Use enum's own values for validation — stays in sync automatically
        valid_values = {member.value for member in DocumentParserType}
        if v not in valid_values:
            raise PydanticCustomError(
                "invalid_choice",
                f"Parser type must be one of: {', '.join(sorted(valid_values))}",
            )
        return DocumentParserType(v)

    # ----- Cross-field validators -----

    @model_validator(mode="after")
    def validate_image_requires_docling(self):
        if (
            self.file_content_type in IMAGE_MIME_TYPES
            and self.parser_type != DocumentParserType.DOCLING
        ):
            raise PydanticCustomError(
                "image_parser_mismatch",
                "Image files require parser_type 'docling'",
            )
        return self


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentStatusData(BaseModel):
    id: uuid.UUID
    name: str
    status: DocumentStatus
    chunk_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListData(BaseModel):
    documents: list[DocumentResponse]
    total: int


class URLIngestRequest(BaseModel):
    url: str
    parser_type: DocumentParserType | None = None
    bot_ids: list[uuid.UUID] | None = None