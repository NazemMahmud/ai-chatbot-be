import re
import uuid
from typing import Any

from pydantic import BaseModel, field_validator, model_validator
from pydantic_core import PydanticCustomError

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    organization_name: str

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        required_fields = {
            "email": "Email is required",
            "password": "Password is required",
            "full_name": "Full name is required",
            "organization_name": "Organization name is required",
        }
        for field, msg in required_fields.items():
            if field not in data:
                raise PydanticCustomError("required", msg)
        return data

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v):
        if not v or not isinstance(v, str) or not v.strip():
            raise PydanticCustomError("invalid", "Email is required")
            
        v = v.strip().lower()
        if not EMAIL_REGEX.match(v):
            raise PydanticCustomError("invalid", "Invalid email format")
        if len(v) > 255:
            raise PydanticCustomError(
                "max_length", "Email must be at most 255 characters"
            )
        return v

    @field_validator("password", mode="before")
    @classmethod
    def validate_password(cls, v):
        if not v or not isinstance(v, str):
            raise PydanticCustomError("invalid", "Password is required")

        if len(v) < 8:
            raise PydanticCustomError(
                "min_length", "Password must be at least 8 characters"
            )

        if len(v) > 128:
            raise PydanticCustomError(
                "max_length", "Password must be at most 128 characters"
            )
        return v

    @field_validator("full_name", mode="before")
    @classmethod
    def validate_full_name(cls, v):
        if not v or not isinstance(v, str) or not v.strip():
            raise PydanticCustomError("invalid", "Full name is required")
        
        v = v.strip()
        if len(v) > 255:
            raise PydanticCustomError(
                "max_length", "Full name must be at most 255 characters"
            )

        return v

    @field_validator("organization_name", mode="before")
    @classmethod
    def validate_organization_name(cls, v):
        if not v or not isinstance(v, str) or not v.strip():
            raise PydanticCustomError("invalid", "Organization name is required")
        
        v = v.strip()
        if len(v) > 255:
            raise PydanticCustomError(
                "max_length", "Organization name must be at most 255 characters"
            )
            
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "email" not in data:
            raise PydanticCustomError("required", "Email is required")
        if "password" not in data:
            raise PydanticCustomError("required", "Password is required")
        return data

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v):
        if not v or not isinstance(v, str) or not v.strip():
            raise PydanticCustomError("invalid", "Email is required")
            
        v = v.strip().lower()
        if not EMAIL_REGEX.match(v):
            raise PydanticCustomError("invalid", "Invalid email format")
        if len(v) > 255:
            raise PydanticCustomError(
                "max_length", "Email must be at most 255 characters"
            )
        return v
    
    @field_validator("password", mode="before")
    @classmethod
    def validate_password(cls, v):
        if not v or not isinstance(v, str):
            raise PydanticCustomError("invalid", "Password is required")

        if len(v) < 8:
            raise PydanticCustomError(
                "min_length", "Password must be at least 8 characters"
            )

        if len(v) > 128:
            raise PydanticCustomError(
                "max_length", "Password must be at most 128 characters"
            )
        return v


class UserInfo(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    organization_name: str | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
