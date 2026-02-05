import uuid
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


class BotCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "name" not in data:
            raise PydanticCustomError("required", "Bot name is required")
        return data
    
    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        if v is None or v == "":
            raise PydanticCustomError("required", "Bot name can't be empty")
        if not isinstance(v, str):
            raise PydanticCustomError("type_error", "Bot name must be a string")
        if not v.strip():
            raise PydanticCustomError("empty", "Bot name cannot be empty")
        if len(v) > 255:
            raise PydanticCustomError("max_length", "Bot name must be at most 255 characters")
        return v.strip()

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v):
        if v and len(v) > 1000:
            raise PydanticCustomError("max_length", "Description must be at most 1000 characters")
        return v


class BotUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            if not isinstance(v, str):
                raise PydanticCustomError("type_error", "Bot name must be a string")
            if not v.strip():
                raise PydanticCustomError("empty", "Bot name cannot be empty")
            if len(v) > 255:
                raise PydanticCustomError("max_length", "Bot name must be at most 255 characters")
            return v.strip()
        return v

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v):
        if not isinstance(v, str):
            raise PydanticCustomError("type_error", "Description must be a string")
        if v and len(v) > 1000:
            raise PydanticCustomError("max_length", "Description must be at most 1000 characters")
        return v.strip()

    @field_validator("is_active", mode="before")
    @classmethod
    def validate_is_active(cls, v):
        if isinstance(v, bool):
            return v
        
        raise PydanticCustomError(
            "bool_type",
            "Is active must be a boolean value"
        )


class BotResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    # created_at: datetime
    # updated_at: datetime

    # system_prompt: str | None
    # model: str
    # temperature: float
    # max_tokens: int

    model_config = {"from_attributes": True}


class BotListData(BaseModel):
    data: list[BotResponse]
    # total: int
