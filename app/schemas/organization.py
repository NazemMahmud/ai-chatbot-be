"""
Schemas for organization management and ownership transfer.
"""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateOrganizationRequest(BaseModel):
    name: str = Field(..., description="Organization name")

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "name" not in data:
            raise PydanticCustomError("required", "Organization name is required")
        return data

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        if not v or not isinstance(v, str) or not v.strip():
            raise PydanticCustomError("invalid", "Organization name is required")
        v = v.strip()
        if len(v) < 2:
            raise PydanticCustomError(
                "min_length", "Organization name must be at least 2 characters"
            )
        if len(v) > 255:
            raise PydanticCustomError(
                "max_length", "Organization name must be at most 255 characters"
            )
        return v


class UpdateOrganizationRequest(BaseModel):
    name: str | None = Field(None, description="New organization name")

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "name" not in data:
            raise PydanticCustomError("required", "Organization name is required")
        return data

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        if v is None:
            return v
        if not isinstance(v, str) or not v.strip():
            raise PydanticCustomError("invalid", "Organization name cannot be empty")
        v = v.strip()
        if len(v) < 2:
            raise PydanticCustomError(
                "min_length", "Organization name must be at least 2 characters"
            )
        if len(v) > 255:
            raise PydanticCustomError(
                "max_length", "Organization name must be at most 255 characters"
            )
        return v


class TransferOwnershipRequest(BaseModel):
    target_user_id: uuid.UUID = Field(..., description="User ID of the member to transfer ownership to")

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "target_user_id" not in data:
            raise PydanticCustomError("required", "Target user ID is required")
        return data

    @field_validator("target_user_id", mode="before")
    @classmethod
    def validate_target_user_id(cls, v):
        if v is None:
            raise PydanticCustomError("required", "Target user ID is required")
        if isinstance(v, str):
            if not v.strip():
                raise PydanticCustomError("required", "Target user ID cannot be empty")
            try:
                return uuid.UUID(v.strip())
            except ValueError:
                raise PydanticCustomError("uuid_parsing", "Target user ID must be a valid UUID")
        if isinstance(v, uuid.UUID):
            return v
        raise PydanticCustomError("type_error", "Target user ID must be a valid UUID string")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    owner_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationData(BaseModel):
    data: OrganizationResponse


class TransferRequestResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str | None = None
    from_user_id: uuid.UUID
    from_user_name: str | None = None
    to_user_id: uuid.UUID
    to_user_name: str | None = None
    accepted_at: datetime | None = None
    declined_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransferRequestListData(BaseModel):
    data: list[TransferRequestResponse]
