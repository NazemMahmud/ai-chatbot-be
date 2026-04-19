import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


class WidgetConfig(BaseModel):
    """Widget appearance configuration. Mirrors the bot model's widget_config JSONB column."""

    position: Optional[Literal["bottom-right", "bottom-left"]] = "bottom-right"
    theme: Optional[Literal["light", "dark", "auto"]] = "light"
    primary_color: Optional[str] = "#6366f1"
    bubble_icon: Optional[Literal["chat"]] = "chat"
    show_branding: Optional[bool] = True

    @field_validator("primary_color", mode="before")
    @classmethod
    def validate_primary_color(cls, v):
        if v is not None:
            if not isinstance(v, str):
                raise PydanticCustomError("type_error", "Primary color must be a string")
            v = v.strip()
            if v and not v.startswith("#"):
                raise PydanticCustomError("invalid", "Primary color must be a hex color (e.g. #6366f1)")
            if v and len(v) not in (4, 7):
                raise PydanticCustomError(
                    "invalid", "Primary color must be a valid hex color (#RGB or #RRGGBB)"
                )
        return v

    model_config = {"from_attributes": True}


class WidgetConfigResponse(BaseModel):
    """Response for GET /{bot_id}/config — widget initialization payload."""

    bot_id: uuid.UUID
    bot_name: str
    welcome_message: str | None = None
    widget_config: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class WidgetChatRequest(BaseModel):
    """Request body for POST /{bot_id}/chat."""

    message: str = Field(..., description="Chat message")
    session_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "message" not in data:
            raise PydanticCustomError("required", "Message is required")
        return data

    @field_validator("message", mode="before")
    @classmethod
    def validate_message(cls, v):
        if not v or not isinstance(v, str) or not v.strip():
            raise PydanticCustomError("invalid", "Message cannot be empty")
        if len(v) > 4000:
            raise PydanticCustomError(
                "max_length", "Message must be at most 4000 characters"
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


class WidgetChatResponse(BaseModel):
    """Response for POST /{bot_id}/chat."""

    session_id: str
    message: str
    sources: list[dict] = Field(default_factory=list)
