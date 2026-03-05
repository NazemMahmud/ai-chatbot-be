"""
Chat API - RAG chat, conversation listing, and message history
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DBSession
from app.services.permissions import PermissionService
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationListData,
    ConversationResponse,
    MessageResponse,
    SourceChunk,
)
from app.schemas.common import ApiResponse
from app.services.chat import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ApiResponse[ChatResponse],
    dependencies=[Depends(PermissionService.Chat.SEND)],
)
async def send_message(
    data: ChatRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Send a message to a bot and get a RAG-powered response."""
    service = ChatService(db)
    result = await service.chat(
        bot_id=data.bot_id,
        message=data.message,
        organization_id=current_user.organization_id,
        session_id=data.session_id,
    )
    return ApiResponse(
        success=True,
        message="Message sent successfully",
        data=result,
        statusCode=status.HTTP_200_OK,
    )


@router.get(
    "/conversations",
    response_model=ApiResponse[ConversationListData],
    dependencies=[Depends(PermissionService.Chat.READ)],
)
async def list_conversations(
    db: DBSession,
    current_user: CurrentUser,
    bot_id: Optional[uuid.UUID] = Query(None, description="Filter by bot ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List conversations for the current organization."""
    service = ChatService(db)
    conversations = await service.list_conversations(
        organization_id=current_user.organization_id,
        bot_id=bot_id,
        limit=limit,
        offset=offset,
    )

    # Map to response format
    conversation_data = []
    for conv in conversations:
        conversation_data.append(
            ConversationResponse(
                id=conv.id,
                bot_id=conv.bot_id,
                bot_name=conv.bot.name if conv.bot else None,
                session_id=conv.session_id,
                message_count=len(conv.messages) if conv.messages else 0,
                created_at=conv.created_at,
            )
        )

    return ApiResponse(
        success=True,
        data=ConversationListData(data=conversation_data),
        statusCode=status.HTTP_200_OK,
    )


@router.get(
    "/conversations/{session_id}/messages",
    response_model=ApiResponse[list[MessageResponse]],
    dependencies=[Depends(PermissionService.Chat.READ)],
)
async def get_conversation_messages(
    session_id: str,
    db: DBSession,
    current_user: CurrentUser,
):
    """Get all messages for a conversation by session ID."""
    service = ChatService(db)
    messages = await service.get_messages(
        session_id=session_id,
        organization_id=current_user.organization_id,
    )

    message_data = []
    for msg in messages:
        sources = None
        if msg.sources:
            sources = [SourceChunk(**s) for s in msg.sources]
        message_data.append(
            MessageResponse(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                sources=sources,
                created_at=msg.created_at,
            )
        )

    return ApiResponse(
        success=True,
        data=message_data,
        statusCode=status.HTTP_200_OK,
    )
