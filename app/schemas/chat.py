import uuid
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    bot_id: uuid.UUID
    message: str
    session_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "bot_id" not in data:
            raise PydanticCustomError("required", "Bot ID is required")
        if "message" not in data:
            raise PydanticCustomError("required", "Message is required")
        return data

    @field_validator("message", mode="before")
    @classmethod
    def validate_message(cls, v):
        if not v or not isinstance(v, str) or not v.strip():
            raise PydanticCustomError("invalid", "Message cannot be empty")
        if len(v) > 5000:
            raise PydanticCustomError(
                "max_length", "Message must be at most 5000 characters"
            )
        return v.strip()

    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, v):
        if v is not None and v != "":
            if not isinstance(v, str):
                raise PydanticCustomError("type_error", "Session ID must be a string")
            if len(v) > 36:
                raise PydanticCustomError(
                    "max_length", "Session ID must be at most 36 characters"
                )
        return v if v else None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SourceChunk(BaseModel):
    content: str
    document_name: str

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    session_id: str
    message: str
    sources: list[SourceChunk] = Field(default_factory=list)


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sources: list[SourceChunk] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: uuid.UUID
    bot_id: uuid.UUID
    bot_name: str | None = None
    session_id: str
    message_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationListData(BaseModel):
    data: list[ConversationResponse]
