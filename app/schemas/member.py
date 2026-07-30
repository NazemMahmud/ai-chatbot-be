"""
Schemas for organization member management and invitations.
Uses dynamic role_id instead of hardcoded role strings.
"""
import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class InviteMemberRequest(BaseModel):
    email: str = Field(..., description="Email of the user to invite")
    role_id: uuid.UUID = Field(..., description="ID of the role to assign")

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "email" not in data:
            raise PydanticCustomError("required", "Email is required")
        if "role_id" not in data:
            raise PydanticCustomError("required", "Role ID is required")
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

    @field_validator("role_id", mode="before")
    @classmethod
    def validate_role_id(cls, v):
        if v is None:
            raise PydanticCustomError("required", "Role ID is required")
        if isinstance(v, str):
            if not v.strip():
                raise PydanticCustomError("required", "Role ID cannot be empty")
            try:
                return uuid.UUID(v.strip())
            except ValueError:
                raise PydanticCustomError("uuid_parsing", "Role ID must be a valid UUID")
        if isinstance(v, uuid.UUID):
            return v
        raise PydanticCustomError("type_error", "Role ID must be a valid UUID string")


class LeaveOrganizationRequest(BaseModel):
    """Self-service leave. Owners must transfer ownership or dissolve when others exist."""

    transfer_to_user_id: uuid.UUID | None = None
    dissolve_organization: bool = False


class LeaveContextMember(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str


class LeaveContextData(BaseModel):
    is_owner: bool
    organization_name: str | None
    solo_owner: bool
    other_members: list[LeaveContextMember]


class ChangeRoleRequest(BaseModel):
    role_id: uuid.UUID = Field(..., description="ID of the new role")

    @model_validator(mode="before")
    @classmethod
    def check_required(cls, data: Any):
        if "role_id" not in data:
            raise PydanticCustomError("required", "Role ID is required")
        return data

    @field_validator("role_id", mode="before")
    @classmethod
    def validate_role_id(cls, v):
        if v is None:
            raise PydanticCustomError("required", "Role ID is required")
        if isinstance(v, str):
            if not v.strip():
                raise PydanticCustomError("required", "Role ID cannot be empty")
            try:
                return uuid.UUID(v.strip())
            except ValueError:
                raise PydanticCustomError("uuid_parsing", "Role ID must be a valid UUID")
        if isinstance(v, uuid.UUID):
            return v
        raise PydanticCustomError("type_error", "Role ID must be a valid UUID string")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class OrgMemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role_id: uuid.UUID
    role_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgMemberListData(BaseModel):
    data: list[OrgMemberResponse]


class MakeInvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    role_id: uuid.UUID
    role_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    role_id: uuid.UUID
    role_name: str | None = None
    accepted_at: datetime | None = None
    declined_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InvitationListData(BaseModel):
    data: list[InvitationResponse]


class PendingInvitationResponse(BaseModel):
    """Invitee-facing: shows invitation details with org info."""
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str | None = None
    role_id: uuid.UUID
    role_name: str | None = None
    invited_by_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PendingInvitationListData(BaseModel):
    data: list[PendingInvitationResponse]
