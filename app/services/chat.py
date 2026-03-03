"""
Chat Service - RAG chat pipeline

Orchestrates: retrieve chunks → build prompt → generate reply → save messages
"""
import logging
import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums.chat import MessageRole
from app.enums.document import DocumentStatus
from app.models import Bot, Conversation, Document, DocumentBot, DocumentChunk, Message
from app.schemas.chat import ChatResponse, SourceChunk
from app.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_service = EmbeddingService()

    # ------------------------------------------------------------------
    # Main chat entry point
    # ------------------------------------------------------------------

    async def chat(
        self,
        bot_id: uuid.UUID,
        message: str,
        organization_id: uuid.UUID,
        session_id: str | None = None,
    ) -> ChatResponse:
        """
        Full RAG chat pipeline:
        1. Validate bot exists and belongs to org
        2. Get or create conversation
        3. Retrieve relevant chunks
        4. Build prompt with context + history
        5. Generate reply via Ollama
        6. Save messages
        7. Return response
        """
        # 1. Validate bot
        bot = await self._get_bot(bot_id, organization_id)

        # 2. Get or create conversation
        conversation, session_id = await self._get_or_create_conversation(
            bot_id, organization_id, session_id
        )

        # 3. Retrieve relevant chunks
        chunks = await self.retrieve_chunks(message, organization_id, bot_id)
        logger.info(f"[CHAT] Got {len(chunks)} chunks for bot={bot_id}, org={organization_id}")

        # 4. Build prompt
        history = await self._get_history(conversation.id, limit=10)
        system_prompt = bot.system_prompt or settings.LLM_SYSTEM_PROMPT
        prompt = self.build_prompt(system_prompt, chunks, history, message)

        # 5. Generate reply
        reply = await self.generate_reply(prompt)

        # 6. Build sources list
        sources = []
        for chunk in chunks:
            doc = await self._get_document_for_chunk(chunk.document_id)
            sources.append(
                SourceChunk(
                    content=chunk.content[:300],
                    document_name=doc.name if doc else "Unknown",
                )
            )

        # 7. Save user message and assistant reply
        source_data = [s.model_dump() for s in sources] if sources else None

        await self._save_message(conversation.id, MessageRole.USER, message)
        await self._save_message(
            conversation.id, MessageRole.ASSISTANT, reply, source_data
        )

        return ChatResponse(
            session_id=session_id,
            message=reply,
            sources=sources,
        )

    # ------------------------------------------------------------------
    # RAG: Retrieve chunks
    # ------------------------------------------------------------------

    # Context budget for chunks.
    # phi4 has 16K tokens (~64K chars). Reserve space for:
    #   - System prompt + instructions: ~1K tokens (~4K chars)
    #   - Conversation history (up to 10 msgs): ~2K tokens (~8K chars)
    #   - LLM response: ~1K tokens (~4K chars)
    # Available for chunks: ~12K tokens = ~48K chars.
    # But LLMs lose attention in very long contexts ("lost in the middle"),
    # so cap at ~30K chars (~30 chunks) for better accuracy.
    MAX_CONTEXT_CHARS = 30000

    async def retrieve_chunks(
        self, query: str, organization_id: uuid.UUID, bot_id: uuid.UUID | None = None,
    ) -> list[DocumentChunk]:
        """
        Smart retrieval with bot-scoped access:
        - If bot has linked documents → use only those
        - If bot has NO linked documents → fallback to all org documents
        Then pick chunks by cosine similarity within context budget.
        """
        logger.info(f"[RAG] retrieve_chunks called for org={organization_id}, bot={bot_id}")

        try:
            query_embedding = await self.embedding_service.embed(query)
            logger.info(f"[RAG] Query embedded OK, vector length={len(query_embedding)}")
        except Exception as e:
            logger.error(f"[RAG] Embedding FAILED: {e}")
            return []

        # Determine which documents to search
        doc_ids = []

        # Check if bot has linked documents
        if bot_id:
            linked_result = await self.db.execute(
                select(DocumentBot.document_id).where(DocumentBot.bot_id == bot_id)
            )
            linked_doc_ids = [row[0] for row in linked_result.all()]

            if linked_doc_ids:
                # Bot has linked docs → filter to only READY ones
                doc_ids_result = await self.db.execute(
                    select(Document.id).where(
                        Document.id.in_(linked_doc_ids),
                        Document.organization_id == organization_id,
                        Document.status == DocumentStatus.READY,
                    )
                )
                doc_ids = [row[0] for row in doc_ids_result.all()]
                logger.info(f"[RAG] Bot has {len(linked_doc_ids)} linked docs, {len(doc_ids)} ready")

        # Fallback: no bot_id or bot has no linked docs → use all org docs
        if not doc_ids:
            doc_ids_result = await self.db.execute(
                select(Document.id).where(
                    Document.organization_id == organization_id,
                    Document.status == DocumentStatus.READY,
                )
            )
            doc_ids = [row[0] for row in doc_ids_result.all()]
            logger.info(f"[RAG] Fallback to all org docs: {len(doc_ids)} ready documents")

        if not doc_ids:
            logger.warning(f"[RAG] No ready documents found for org {organization_id}")
            return []

        # Count total chunks
        count_result = await self.db.execute(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id.in_(doc_ids)
            )
        )
        total_chunks = count_result.scalar() or 0
        max_chunks = self.MAX_CONTEXT_CHARS // settings.CHUNK_SIZE
        logger.info(f"[RAG] total_chunks={total_chunks}, max_chunks={max_chunks}")

        if total_chunks <= max_chunks:
            # Small dataset: send ALL chunks ordered by relevance
            stmt = (
                select(DocumentChunk)
                .where(DocumentChunk.document_id.in_(doc_ids))
                .order_by(
                    DocumentChunk.embedding.cosine_distance(query_embedding)
                )
            )
            logger.info(f"[RAG] Small dataset ({total_chunks} chunks) — sending all")
        else:
            # Large dataset: pick most relevant subset
            stmt = (
                select(DocumentChunk)
                .where(DocumentChunk.document_id.in_(doc_ids))
                .order_by(
                    DocumentChunk.embedding.cosine_distance(query_embedding)
                )
                .limit(max_chunks)
            )
            logger.info(
                f"[RAG] Large dataset ({total_chunks} chunks) — sending top {max_chunks}"
            )

        try:
            result = await self.db.execute(stmt)
            chunks = list(result.scalars().all())
            logger.info(f"[RAG] Retrieved {len(chunks)} chunks from DB")
            if chunks:
                logger.info(f"[RAG] First chunk preview: {chunks[0].content[:100]}...")
            return chunks
        except Exception as e:
            logger.error(f"[RAG] Chunk query FAILED: {e}")
            return []

    # ------------------------------------------------------------------
    # RAG: Build prompt
    # ------------------------------------------------------------------

    def build_prompt(
        self,
        system_prompt: str,
        context_chunks: list[DocumentChunk],
        history: list[Message],
        user_message: str,
    ) -> list[dict]:
        """Build the message list for the LLM."""
        if context_chunks:
            context_text = "\n\n".join(
                f"[Source {i+1}] {chunk.content}"
                for i, chunk in enumerate(context_chunks)
            )
            full_system = (
                f"{system_prompt}\n\n"
                "## INSTRUCTIONS\n"
                "1. Answer using ONLY the document context below.\n"
                "2. Read EVERY source carefully from start to end before answering.\n"
                "3. Be COMPLETE — include ALL matching items from ALL sources. "
                "Do NOT stop early or skip any source.\n"
                "4. If asked whether something exists, search ALL sources "
                "before saying it does not exist.\n"
                "5. Be CONCISE — answer directly without unnecessary elaboration.\n\n"
                f"## DOCUMENT CONTEXT\n{context_text}"
            )
        else:
            full_system = (
                f"{system_prompt}\n\n"
                "No document context is available. Let the user know that no relevant "
                "documents were found and answer based on general knowledge if possible."
            )

        messages = [{"role": "system", "content": full_system}]

        # Add conversation history (trim long messages to save context budget)
        for msg in history:
            content = msg.content
            if len(content) > 500:
                content = content[:500] + "..."
            messages.append({"role": msg.role, "content": content})

        # Add the current user message
        messages.append({"role": "user", "content": user_message})

        return messages

    # ------------------------------------------------------------------
    # RAG: Generate reply via Ollama
    # ------------------------------------------------------------------

    async def generate_reply(self, prompt: list[dict]) -> str:
        """Send prompt to Ollama LLM and return the assistant's reply."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": settings.OLLAMA_LLM_MODEL,
                        "messages": prompt,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "I could not generate a response.")
        except httpx.TimeoutException:
            logger.error("Ollama LLM request timed out")
            return "Sorry, the response took too long. Please try again."
        except Exception as e:
            logger.error(f"Ollama LLM error: {e}")
            return "Sorry, I encountered an error while generating a response."

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    async def list_conversations(
        self,
        organization_id: uuid.UUID,
        bot_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        """List conversations for an organization, optionally filtered by bot."""
        query = select(Conversation).where(
            Conversation.organization_id == organization_id
        )

        if bot_id is not None:
            query = query.where(Conversation.bot_id == bot_id)

        query = query.order_by(Conversation.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_messages(
        self,
        session_id: str,
        organization_id: uuid.UUID,
    ) -> list[Message]:
        """Get all messages for a conversation by session_id."""
        conversation = await self._get_conversation_by_session(
            session_id, organization_id
        )
        return list(conversation.messages) if conversation.messages else []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_bot(self, bot_id: uuid.UUID, organization_id: uuid.UUID) -> Bot:
        result = await self.db.execute(
            select(Bot).where(
                Bot.id == bot_id,
                Bot.organization_id == organization_id,
                Bot.is_active.is_(True),
            )
        )
        bot = result.scalar_one_or_none()
        if not bot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found or inactive",
            )
        return bot

    async def _get_or_create_conversation(
        self,
        bot_id: uuid.UUID,
        organization_id: uuid.UUID,
        session_id: str | None,
    ) -> tuple[Conversation, str]:
        """Get existing conversation by session_id or create a new one."""
        if session_id:
            result = await self.db.execute(
                select(Conversation).where(
                    Conversation.session_id == session_id,
                    Conversation.organization_id == organization_id,
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation:
                return conversation, session_id

        # Create new conversation
        session_id = str(uuid.uuid4())
        conversation = Conversation(
            bot_id=bot_id,
            organization_id=organization_id,
            session_id=session_id,
        )
        self.db.add(conversation)
        await self.db.flush()
        return conversation, session_id

    async def _get_conversation_by_session(
        self, session_id: str, organization_id: uuid.UUID
    ) -> Conversation:
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.session_id == session_id,
                Conversation.organization_id == organization_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return conversation

    async def _get_history(
        self, conversation_id: uuid.UUID, limit: int = 10
    ) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        messages = list(result.scalars().all())
        return messages[-limit:] if len(messages) > limit else messages

    async def _save_message(
        self,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: str,
        sources: list[dict] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources,
        )
        self.db.add(message)
        await self.db.flush()
        return message

    async def _get_document_for_chunk(self, document_id: uuid.UUID) -> Document | None:
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()
