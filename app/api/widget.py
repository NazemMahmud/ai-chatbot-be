import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import DBSession
from app.schemas.chat import WidgetChatRequest, WidgetConfigResponse
from app.services.rag import RAGService

router = APIRouter()


@router.get("/{bot_id}/config", response_model=WidgetConfigResponse)
async def get_widget_config(bot_id: uuid.UUID, db: DBSession):
    """Public endpoint — returns bot name, welcome message, theme config. No auth required."""
    service = RAGService(db)
    return await service.get_widget_config(bot_id)


@router.post("/{bot_id}/chat")
async def widget_chat(
    bot_id: uuid.UUID,
    data: WidgetChatRequest,
    db: DBSession,
):
    """Public chat endpoint for widget users. Uses session_id, rate-limited."""
    service = RAGService(db)

    async def event_stream():
        async for chunk in service.widget_chat(
            bot_id=bot_id,
            message=data.message,
            session_id=data.session_id,
            history=data.history,
        ):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")
