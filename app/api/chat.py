import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DBSession
from app.schemas.chat import ChatRequest, ConversationResponse, MessageResponse
from app.services.rag import RAGService

router = APIRouter()


@router.post("/bots/{bot_id}/chat")
async def chat(
    bot_id: uuid.UUID,
    data: ChatRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Streaming SSE response for authenticated dashboard users."""
    service = RAGService(db)

    async def event_stream():
        async for chunk in service.chat(
            bot_id=bot_id,
            message=data.message,
            conversation_id=data.conversation_id,
            user_id=current_user.id,
            history=data.history,
        ):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/bots/{bot_id}/conversations", response_model=list[ConversationResponse])
async def list_conversations(bot_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    """List conversations for a bot."""
    service = RAGService(db)
    return await service.list_conversations(bot_id, current_user.id)


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
async def get_messages(conv_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    """Get message history for a conversation."""
    service = RAGService(db)
    messages = await service.get_messages(conv_id, current_user.id)
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return messages
