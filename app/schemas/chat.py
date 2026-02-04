import uuid
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: uuid.UUID | None = None
    history: list[dict] | None = None  # [{"role": "user"|"assistant", "content": "..."}]


class WidgetChatRequest(BaseModel):
    message: str
    session_id: str
    history: list[dict] | None = None


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sources: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: uuid.UUID
    bot_id: uuid.UUID
    session_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WidgetConfigResponse(BaseModel):
    bot_id: uuid.UUID
    name: str
    welcome_message: str | None
    widget_config: dict | None
