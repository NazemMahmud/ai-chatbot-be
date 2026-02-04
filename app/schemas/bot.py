import uuid
from datetime import datetime

from pydantic import BaseModel


class BotCreate(BaseModel):
    name: str
    system_prompt: str | None = None
    welcome_message: str | None = None
    model: str = "smollm3:3b"
    temperature: float = 0.7
    show_citations: bool = True
    allowed_domains: list[str] | None = None


class BotUpdate(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    welcome_message: str | None = None
    model: str | None = None
    temperature: float | None = None
    show_citations: bool | None = None
    allowed_domains: list[str] | None = None
    is_active: bool | None = None


class BotResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    slug: str
    system_prompt: str | None
    welcome_message: str | None
    model: str
    temperature: float
    show_citations: bool
    allowed_domains: list[str] | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class BotListResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    model: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
