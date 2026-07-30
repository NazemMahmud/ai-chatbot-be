"""
Schemas for role and permission management.
"""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class RoleCreateRequest(BaseModel):
    name: str = Field(..., description="Role name")
    description: str | None = None
    permission_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="List of permission UUIDs to assign to the role",
    )

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "name" not in data:
            raise PydanticCustomError("required", "Role name is required")
        return data

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        if not v or not isinstance(v, str) or not v.strip():
            raise PydanticCustomError("invalid", "Role name is required")
        v = v.strip()
        if len(v) > 100:
            raise PydanticCustomError(
                "max_length", "Role name must be at most 100 characters"
            )
        if len(v) < 2:
            raise PydanticCustomError(
                "min_length", "Role name must be at least 2 characters"
            )
        return v

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v):
        if v is not None:
            if not isinstance(v, str):
                raise PydanticCustomError("type_error", "Description must be a string")
            if len(v) > 500:
                raise PydanticCustomError(
                    "max_length", "Description must be at most 500 characters"
                )
        return v

    @field_validator("permission_ids", mode="before")
    @classmethod
    def validate_permission_ids(cls, v):
        if v is None:
            return []
        if not isinstance(v, list):
            raise PydanticCustomError("type_error", "Permission IDs must be a list")
        if len(v) > 50:
            raise PydanticCustomError(
                "max_length", "Permission IDs can contain at most 50 items"
            )
        result = []
        for item in v:
            try:
                result.append(uuid.UUID(str(item)))
            except (ValueError, AttributeError):
                raise PydanticCustomError(
                    "uuid_parsing", f"Invalid UUID in permission_ids: {item}"
                )
        return result


class RoleUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    permission_ids: list[uuid.UUID] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            if not isinstance(v, str):
                raise PydanticCustomError("type_error", "Role name must be a string")
            v = v.strip()
            if not v:
                raise PydanticCustomError("invalid", "Role name cannot be empty")
            if len(v) > 100:
                raise PydanticCustomError(
                    "max_length", "Role name must be at most 100 characters"
                )
            if len(v) < 2:
                raise PydanticCustomError(
                    "min_length", "Role name must be at least 2 characters"
                )
            return v
        return v

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v):
        if v is not None:
            if not isinstance(v, str):
                raise PydanticCustomError("type_error", "Description must be a string")
            if len(v) > 500:
                raise PydanticCustomError(
                    "max_length", "Description must be at most 500 characters"
                )
        return v

    @field_validator("permission_ids", mode="before")
    @classmethod
    def validate_permission_ids(cls, v):
        if v is None:
            return None
        if not isinstance(v, list):
            raise PydanticCustomError("type_error", "Permission IDs must be a list")
        if len(v) > 50:
            raise PydanticCustomError(
                "max_length", "Permission IDs can contain at most 50 items"
            )
        result = []
        for item in v:
            try:
                result.append(uuid.UUID(str(item)))
            except (ValueError, AttributeError):
                raise PydanticCustomError(
                    "uuid_parsing", f"Invalid UUID in permission_ids: {item}"
                )
        return result


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PermissionResponse(BaseModel):
    id: uuid.UUID
    resource: str
    action: str
    description: str | None = None

    model_config = {"from_attributes": True}


class PermissionListData(BaseModel):
    data: list[PermissionResponse]


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool
    permissions: list[PermissionResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleDetailResponse(BaseModel):
    """Role detail for edit page — permission_ids only (map against permission picker)."""
    id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool
    permission_ids: list[uuid.UUID] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleListData(BaseModel):
    data: list[RoleResponse]


class RolePickerItem(BaseModel):
    """Lightweight role representation for picker/select dropdowns (e.g. invite member form)."""
    id: uuid.UUID
    name: str
    is_system: bool

    model_config = {"from_attributes": True}


class RolePickerListData(BaseModel):
    data: list[RolePickerItem]


# ---------------------------------------------------------------------------
# Permission picker (grouped by resource for checkbox UI)
# ---------------------------------------------------------------------------


class PermissionPickerItem(BaseModel):
    """Single permission for picker checkbox."""
    id: uuid.UUID
    action: str
    description: str | None = None

    model_config = {"from_attributes": True}


class PermissionGroupResponse(BaseModel):
    """Permissions grouped by resource for picker UI."""
    resource: str
    permissions: list[PermissionPickerItem]


class PermissionPickerListData(BaseModel):
    data: list[PermissionGroupResponse]
