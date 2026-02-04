"""
RAG service — orchestrates retrieval-augmented generation.
Embeds user query, searches pgvector, builds prompt, streams LLM response.
"""

import uuid
from collections.abc import AsyncGenerator

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot
from app.models.conversation import Conversation, Message
from app.schemas.chat import WidgetConfigResponse
from app.services.chat import ChatService
from app.services.embedding import EmbeddingService


class RAGService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_service = EmbeddingService()
        self.chat_service = ChatService()

    async def chat(
        self,
        bot_id: uuid.UUID,
        message: str,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
        history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """RAG chat for authenticated dashboard users."""
        bot = await self._get_bot(bot_id)
        if not bot:
            yield 'data: {"error": "Bot not found"}\n\n'
            return

        # Embed query and search for relevant chunks
        context_chunks = await self._retrieve_context(bot_id, message)

        # Build messages for the LLM
        messages = self._build_messages(bot, message, context_chunks, history)

        # Stream response
        async for token in self.chat_service.generate_response(
            messages=messages,
            model=bot.model,
            temperature=bot.temperature,
        ):
            yield f"data: {token}\n\n"

        yield "data: [DONE]\n\n"

    async def widget_chat(
        self,
        bot_id: uuid.UUID,
        message: str,
        session_id: str,
        history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """RAG chat for anonymous widget users (session-based)."""
        bot = await self._get_bot(bot_id)
        if not bot:
            yield 'data: {"error": "Bot not found"}\n\n'
            return

        # TODO: rate limiting by session_id
        # TODO: domain allowlist check

        context_chunks = await self._retrieve_context(bot_id, message)
        messages = self._build_messages(bot, message, context_chunks, history)

        async for token in self.chat_service.generate_response(
            messages=messages,
            model=bot.model,
            temperature=bot.temperature,
        ):
            yield f"data: {token}\n\n"

        yield "data: [DONE]\n\n"

    async def _get_bot(self, bot_id: uuid.UUID) -> Bot | None:
        result = await self.db.execute(select(Bot).where(Bot.id == bot_id))
        return result.scalar_one_or_none()

    async def _retrieve_context(
        self, bot_id: uuid.UUID, query: str, limit: int = 5
    ) -> list[dict]:
        """Embed query and perform vector similarity search."""
        query_embedding = await self.embedding_service.generate_embedding(query)

        result = await self.db.execute(
            text("""
                SELECT content, metadata,
                       1 - (embedding <=> :query_embedding::vector) as similarity
                FROM document_chunks
                WHERE bot_id = :bot_id
                ORDER BY embedding <=> :query_embedding::vector
                LIMIT :limit
            """),
            {
                "bot_id": str(bot_id),
                "query_embedding": str(query_embedding),
                "limit": limit,
            },
        )
        rows = result.fetchall()
        return [
            {"content": row.content, "metadata": row.metadata, "similarity": row.similarity}
            for row in rows
        ]

    def _build_messages(
        self,
        bot: Bot,
        message: str,
        context_chunks: list[dict],
        history: list[dict] | None = None,
    ) -> list[dict]:
        """Build the prompt with system prompt, context, history, and user message."""
        context_text = "\n\n".join(
            [
                f"[Source: {c['metadata'].get('source', 'Unknown')}]\n{c['content']}"
                for c in context_chunks
            ]
        )

        system_prompt = f"""{bot.system_prompt or 'You are a helpful assistant.'}

Use the following context to answer the user's question.
If you cannot find the answer in the context, say so honestly.
Always cite your sources when possible.

Context:
{context_text}
"""

        messages = [{"role": "system", "content": system_prompt}]

        if history:
            messages.extend(history[-10:])

        messages.append({"role": "user", "content": message})
        return messages

    async def list_conversations(
        self, bot_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.bot_id == bot_id)
            .order_by(Conversation.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_messages(
        self, conv_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Message] | None:
        # Verify conversation exists
        conv_result = await self.db.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            return None

        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())

    async def get_widget_config(self, bot_id: uuid.UUID) -> WidgetConfigResponse:
        bot = await self._get_bot(bot_id)
        if not bot:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")

        return WidgetConfigResponse(
            bot_id=bot.id,
            name=bot.name,
            welcome_message=bot.welcome_message,
            widget_config=bot.widget_config,
        )
