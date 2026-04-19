"""
Widget API - Public endpoints for the embeddable chat widget.

No authentication required. Rate-limited per IP and session.
"""
import uuid
import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession
from app.models import Document, DocumentBot
from app.enums.document import DocumentStatus
from app.schemas.common import ApiResponse
from app.schemas.widget import WidgetChatRequest, WidgetChatResponse, WidgetConfigResponse
from app.schemas.chat import SourceChunk
from app.services.bot import BotService
from app.services.chat import ChatService
from app.services.rate_limiter import check_widget_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/widget", tags=["widget"])


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/config/{bot_id}", response_model=ApiResponse[WidgetConfigResponse])
async def get_widget_config(
    bot_id: uuid.UUID,
    request: Request,
    db: DBSession,
):
    """Get bot config for widget initialization. Public endpoint."""
    bot = await BotService(db).get_bot_or_raise(bot_id, require_active=True)
    BotService.check_origin(request, bot)

    return ApiResponse(
        success=True,
        data=WidgetConfigResponse(
            bot_id=bot.id,
            bot_name=bot.name,
            welcome_message=bot.welcome_message,
            widget_config=bot.widget_config or {},
        ),
    )


@router.post("/chat/{bot_id}", response_model=ApiResponse[WidgetChatResponse])
async def widget_chat(
    bot_id: uuid.UUID,
    data: WidgetChatRequest,
    request: Request,
    db: DBSession,
):
    """Send a message via the widget. Public endpoint with rate limiting."""
    # client_ip = _get_client_ip(request)

    # # Rate limit check (enable when WIDGET_RATE_LIMIT_PER_MINUTE is configured)
    # allowed = await check_widget_rate_limit(client_ip, data.session_id)
    # if not allowed:
    #     raise HTTPException(
    #         status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    #         detail="Rate limit exceeded. Please try again later.",
    #     )

    # Find bot
    bot = await BotService(db).get_bot_or_raise(bot_id, require_active=True)
    BotService.check_origin(request, bot)

    # Check bot has documents
    doc_count = await db.execute(
        select(func.count(DocumentBot.document_id)).where(
            DocumentBot.bot_id == bot_id,
        )
    )
    count = doc_count.scalar() or 0

    if count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This bot has no documents configured. Please contact the administrator.",
        )

    # Check at least one document is ready
    ready_count = await db.execute(
        select(func.count(Document.id))
        .join(DocumentBot, Document.id == DocumentBot.document_id)
        .where(
            DocumentBot.bot_id == bot_id,
            Document.status == DocumentStatus.READY,
            Document.deleted_at.is_(None),
        )
    )
    if (ready_count.scalar() or 0) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot documents are still processing. Please try again later.",
        )

    # Use ChatService for RAG pipeline
    service = ChatService(db)
    chat_result = await service.chat(
        bot_id=bot_id,
        message=data.message,
        organization_id=bot.organization_id,
        session_id=data.session_id,
    )

    return ApiResponse(
        success=True,
        data=WidgetChatResponse(
            session_id=chat_result.session_id,
            message=chat_result.message,
            sources=[
                {"content": s.content, "document_name": s.document_name}
                for s in chat_result.sources
            ],
        ),
    )


@router.get("/history/{bot_id}/{session_id}", response_model=ApiResponse)
async def widget_history(
    bot_id: uuid.UUID,
    session_id: str,
    request: Request,
    db: DBSession,
):
    """Get conversation history for a widget session. Public endpoint."""
    bot = await BotService(db).get_bot_or_raise(bot_id, require_active=True)
    BotService.check_origin(request, bot)

    service = ChatService(db)
    try:
        messages = await service.get_messages(
            session_id=session_id,
            organization_id=bot.organization_id,
        )
    except HTTPException:
        return ApiResponse(success=True, data=[])

    message_data = []
    for msg in messages:
        message_data.append({
            "role": msg.role,
            "content": msg.content,
            "sources": msg.sources
        })

    return ApiResponse(success=True, data=message_data)
