"""
Unified integration schemas — validates dynamically based on channel_type.

To add a new platform:
1. Add its fields as Optional to IntegrationSetupRequest
2. Add an entry to CHANNEL_REQUIRED_FIELDS
3. Add field max lengths to _FIELD_MAX_LENGTHS
"""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.enums.channel import ChannelType, WebHookChannelType


# ---------------------------------------------------------------------------
# Channel-specific field registry (single source of truth)
# ---------------------------------------------------------------------------

# Required fields per channel type — key: field name, value: error message
CHANNEL_REQUIRED_FIELDS: dict[ChannelType, dict[str, str]] = {
    ChannelType.WHATSAPP: {
        "phone_number_id": "Phone number ID is required for WhatsApp",
        "access_token": "Access token is required for WhatsApp",
        "verify_token": "Verify token is required for WhatsApp",
    },
    ChannelType.TELEGRAM: {
        "bot_token": "Bot token is required for Telegram",
    },
}

# Max lengths for string fields
_FIELD_MAX_LENGTHS: dict[str, int] = {
    "phone_number_id": 255,
    "access_token": 1000,
    "verify_token": 255,
    "bot_token": 500,
}


# ---------------------------------------------------------------------------
# Unified setup request
# ---------------------------------------------------------------------------


class IntegrationSetupRequest(BaseModel):
    """
    All webhook integration setup requests.
    channel_type is injected from the URL path via a Depends before validation.
    All validation — including per-channel required fields — happens here.
    """

    channel_type: WebHookChannelType
    bot_id: uuid.UUID = Field(..., description="Bot to link channel to")

    # WhatsApp fields
    phone_number_id: str | None = None
    access_token: str | None = None
    verify_token: str | None = None

    # Telegram fields
    bot_token: str | None = None

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "bot_id" not in data:
            raise PydanticCustomError("required", "Bot ID is required")
        return data

    @field_validator("bot_id", mode="before")
    @classmethod
    def validate_bot_id(cls, v: Any) -> uuid.UUID:
        if v is None:
            raise PydanticCustomError("required", "Bot ID is required")
        if isinstance(v, str):
            if not v.strip():
                raise PydanticCustomError("required", "Bot ID cannot be empty")
            try:
                return uuid.UUID(v.strip())
            except ValueError:
                raise PydanticCustomError("uuid_parsing", "Bot ID must be a valid UUID")
        if isinstance(v, uuid.UUID):
            return v
        raise PydanticCustomError("type_error", "Bot ID must be a valid UUID string")

    @field_validator(
        "phone_number_id", "access_token", "verify_token", "bot_token",
        mode="before",
    )
    @classmethod
    def validate_string_field(cls, v: Any, info) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str) or not v.strip():
            return None
        v = v.strip()
        max_len = _FIELD_MAX_LENGTHS.get(info.field_name, 1000)
        if len(v) > max_len:
            raise PydanticCustomError(
                "max_length",
                f"{info.field_name} must be at most {max_len} characters",
            )
        return v

    @model_validator(mode="after")
    def validate_by_channel(self):
        required = CHANNEL_REQUIRED_FIELDS.get(self.channel_type)
        if required is None:
            raise ValueError(
                f"Setup is not supported for {self.channel_type.value}"
            )
        for field_name, error_msg in required.items():
            if not getattr(self, field_name):
                raise ValueError(error_msg)
        return self

    def get_config(self) -> dict:
        """Extract platform-specific config dict from validated fields."""
        required = CHANNEL_REQUIRED_FIELDS.get(self.channel_type, {})
        return {field: getattr(self, field) for field in required}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ChannelStatusResponse(BaseModel):
    bot_id: uuid.UUID
    channel_type: str
    is_active: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class WebhookInfoResponse(BaseModel):
    webhook_url: str
    channel_type: str
    bot_id: uuid.UUID
