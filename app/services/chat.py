"""
Chat Service - Production RAG chat pipeline

Pipeline:
1. Entity lookup (fast, deterministic — for exhaustive queries)
2. Broad retrieval: cosine top-50 + BM25 keyword top-30 → merge
3. Rerank: cross-encoder scores → keep top 12-15
4. Expand: grab neighbor chunks (±1) for completeness
5. Build prompt: system + citations rule + context + history + question
6. Generate: send to LLM
7. Save: persist messages
"""
import logging
import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums.chat import MessageRole
from app.enums.document import DocumentStatus
from app.models import (
    Bot,
    Conversation,
    Document,
    DocumentBot,
    DocumentChunk,
    DocumentEntity,
    Message,
)
from app.schemas.chat import ChatResponse, SourceChunk
from app.services.embedding import EmbeddingService
from app.services.reranker import rerank

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

# How many chunks to retrieve in the broad first pass (cheap, fast)
BROAD_COSINE_K = 50
BROAD_BM25_K = 30

# How many chunks to keep after cross-encoder reranking
RERANK_TOP_K = 15

# Max conversation history messages to include
HISTORY_LIMIT = 10
HISTORY_MSG_MAX_CHARS = 500


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
        """Full RAG chat pipeline."""
        # 1. Validate bot
        bot = await self._get_bot(bot_id, organization_id)

        # 2. Get or create conversation
        conversation, session_id = await self._get_or_create_conversation(
            bot_id, organization_id, session_id
        )

        # 3. Resolve document scope
        doc_ids = await self._resolve_doc_ids(bot_id, organization_id)

        # 4. Check for entity-based answer (exhaustive queries)
        entity_context = await self._entity_lookup(message, doc_ids)

        # 5. Retrieve relevant chunks (broad → rerank → expand)
        chunks = await self.retrieve_chunks(message, doc_ids)
        logger.info(
            f"[CHAT] {len(chunks)} chunks after full pipeline "
            f"for bot={bot_id}, org={organization_id}"
        )

        # 6. Build prompt
        history = await self._get_history(conversation.id, limit=HISTORY_LIMIT)
        system_prompt = bot.system_prompt or settings.LLM_SYSTEM_PROMPT
        prompt = self.build_prompt(
            system_prompt, chunks, history, message, entity_context
        )

        # 7. Generate reply
        reply = await self.generate_reply(prompt)

        # 8. Build sources list (deduplicated by document)
        sources = []
        seen_docs: set[uuid.UUID] = set()
        for chunk in chunks:
            if chunk.document_id not in seen_docs:
                doc = await self._get_document_for_chunk(chunk.document_id)
                page = (chunk.metadata_ or {}).get("page_number")
                page_str = f" (Page {page})" if page else ""
                sources.append(
                    SourceChunk(
                        content=chunk.content[:300],
                        document_name=(doc.name if doc else "Unknown") + page_str,
                    )
                )
                seen_docs.add(chunk.document_id)

        # 9. Save messages
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
    # Document scope resolution
    # ------------------------------------------------------------------

    async def _resolve_doc_ids(
        self, bot_id: uuid.UUID | None, organization_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """
        Determine which documents to search.
        - Bot has linked docs → use only those
        - Bot has NO linked docs → fallback to all org docs
        """
        doc_ids: list[uuid.UUID] = []

        if bot_id:
            linked = await self.db.execute(
                select(DocumentBot.document_id).where(
                    DocumentBot.bot_id == bot_id
                )
            )
            linked_ids = [row[0] for row in linked.all()]

            if linked_ids:
                result = await self.db.execute(
                    select(Document.id).where(
                        Document.id.in_(linked_ids),
                        Document.organization_id == organization_id,
                        Document.status == DocumentStatus.READY,
                    )
                )
                doc_ids = [row[0] for row in result.all()]
                logger.info(
                    f"[RAG] Bot {bot_id}: {len(linked_ids)} linked, "
                    f"{len(doc_ids)} ready"
                )

        if not doc_ids:
            result = await self.db.execute(
                select(Document.id).where(
                    Document.organization_id == organization_id,
                    Document.status == DocumentStatus.READY,
                )
            )
            doc_ids = [row[0] for row in result.all()]
            logger.info(f"[RAG] Fallback to all org docs: {len(doc_ids)} ready")

        return doc_ids

    # ------------------------------------------------------------------
    # Entity lookup (for exhaustive queries)
    # ------------------------------------------------------------------

    async def _entity_lookup(
        self, query: str, doc_ids: list[uuid.UUID]
    ) -> str | None:
        """
        Check if the query is an exhaustive lookup (e.g. "list all characters",
        "what are the names", "who are the people"). If so, query the
        document_entities table for a deterministic answer.

        Returns a context string to inject into the prompt, or None.
        """
        if not doc_ids:
            return None

        # Simple heuristic: detect exhaustive queries
        q = query.lower().strip()
        exhaustive_patterns = [
            ("person", [
                "all character", "all the character",
                "character name", "characters name",
                "list of character", "list character",
                "who are the", "all people", "all person",
                "all the people", "names of character",
                "name of character", "every character",
                "all names", "all the names",
            ]),
            ("organization", [
                "all compan", "all the compan", "list compan",
                "all organization", "list organization",
                "every company", "every organization",
            ]),
            ("location", [
                "all location", "all the location", "list location",
                "all place", "all the place", "list place",
                "every location", "every place",
            ]),
        ]

        matched_type = None
        for etype, patterns in exhaustive_patterns:
            if any(p in q for p in patterns):
                matched_type = etype
                break

        if not matched_type:
            return None

        # Query the entity table
        result = await self.db.execute(
            select(
                DocumentEntity.entity_value,
                func.sum(DocumentEntity.count).label("total"),
            )
            .where(
                DocumentEntity.document_id.in_(doc_ids),
                DocumentEntity.entity_type == matched_type,
            )
            .group_by(DocumentEntity.entity_value)
            .order_by(func.sum(DocumentEntity.count).desc())
        )
        entities = result.all()

        if not entities:
            return None

        entity_list = ", ".join(row[0] for row in entities)
        logger.info(
            f"[RAG] Entity lookup: {matched_type} → "
            f"{len(entities)} unique entities found"
        )

        return (
            f"## ENTITY INDEX ({matched_type.upper()}S found in documents)\n"
            f"The following {matched_type}s were extracted from the documents: "
            f"{entity_list}\n"
            f"This list is comprehensive. Include ALL of these in your answer "
            f"if the user asks for a complete list."
        )

    # ------------------------------------------------------------------
    # RAG: Full retrieval pipeline
    # ------------------------------------------------------------------

    async def retrieve_chunks(
        self, query: str, doc_ids: list[uuid.UUID]
    ) -> list[DocumentChunk]:
        """
        Full retrieval pipeline:
        1. Embed query
        2. Cosine similarity: top BROAD_COSINE_K
        3. BM25 keyword: top BROAD_BM25_K
        4. Merge + deduplicate
        5. Rerank with cross-encoder → top RERANK_TOP_K
        6. Expand with neighbor chunks (±1)
        """
        if not doc_ids:
            logger.warning("[RAG] No document IDs provided")
            return []

        # 1. Embed query
        try:
            query_embedding = await self.embedding_service.embed(query)
            logger.info(f"[RAG] Query embedded, dim={len(query_embedding)}")
        except Exception as e:
            logger.error(f"[RAG] Embedding FAILED: {e}")
            return []

        # 2. Cosine similarity retrieval
        cosine_stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id.in_(doc_ids))
            .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
            .limit(BROAD_COSINE_K)
        )
        try:
            cosine_result = await self.db.execute(cosine_stmt)
            cosine_chunks = list(cosine_result.scalars().all())
            logger.info(f"[RAG] Cosine: {len(cosine_chunks)} chunks")
        except Exception as e:
            logger.error(f"[RAG] Cosine query FAILED: {e}")
            cosine_chunks = []

        # 3. BM25 keyword retrieval
        bm25_chunks = await self._bm25_search(query, doc_ids)
        logger.info(f"[RAG] BM25: {len(bm25_chunks)} chunks")

        # 4. Merge + deduplicate (cosine results take priority)
        seen_ids: set[uuid.UUID] = set()
        merged: list[DocumentChunk] = []

        for chunk in cosine_chunks:
            if chunk.id not in seen_ids:
                merged.append(chunk)
                seen_ids.add(chunk.id)

        for chunk in bm25_chunks:
            if chunk.id not in seen_ids:
                merged.append(chunk)
                seen_ids.add(chunk.id)

        logger.info(f"[RAG] Merged: {len(merged)} unique chunks")

        # 5. Rerank with cross-encoder
        reranked = rerank(query, merged, top_k=RERANK_TOP_K)
        logger.info(f"[RAG] Reranked: {len(reranked)} chunks")

        # 6. Expand with neighbor chunks
        expanded = await self._expand_neighbors(reranked)
        logger.info(f"[RAG] After neighbor expansion: {len(expanded)} chunks")

        return expanded

    async def _bm25_search(
        self, query: str, doc_ids: list[uuid.UUID]
    ) -> list[DocumentChunk]:
        """
        Full-text keyword search using PostgreSQL tsvector.
        Falls back gracefully if the search_vector column doesn't exist yet.
        """
        try:
            # Build tsquery from user's natural language query
            # plainto_tsquery handles natural language → tsquery conversion
            stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id.in_(doc_ids),
                    DocumentChunk.search_vector.op("@@")(
                        func.plainto_tsquery("english", query)
                    ),
                )
                .order_by(
                    func.ts_rank_cd(
                        DocumentChunk.search_vector,
                        func.plainto_tsquery("english", query),
                    ).desc()
                )
                .limit(BROAD_BM25_K)
            )
            result = await self.db.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            # Graceful fallback if search_vector column doesn't exist yet
            # (before migration runs)
            logger.debug(f"[RAG] BM25 search unavailable: {e}")
            return []

    async def _expand_neighbors(
        self, chunks: list[DocumentChunk]
    ) -> list[DocumentChunk]:
        """
        For each chunk, also fetch chunk_index ± 1 from the same document.
        This catches information that spans chunk boundaries.
        Deduplicates and sorts by (document_id, chunk_index).
        """
        if not chunks:
            return []

        # Collect neighbor indices to fetch
        needed: set[tuple[uuid.UUID, int]] = set()  # (doc_id, chunk_index)
        existing_ids: set[uuid.UUID] = {c.id for c in chunks}

        for chunk in chunks:
            if chunk.chunk_index is not None:
                doc_id = chunk.document_id
                needed.add((doc_id, chunk.chunk_index - 1))
                needed.add((doc_id, chunk.chunk_index))
                needed.add((doc_id, chunk.chunk_index + 1))

        if not needed:
            # No chunk_index available (old data before migration)
            return chunks

        # Fetch all needed chunks in one query
        # Build OR conditions for each (doc_id, chunk_index) pair
        conditions = [
            and_(
                DocumentChunk.document_id == doc_id,
                DocumentChunk.chunk_index == idx,
            )
            for doc_id, idx in needed
            if idx >= 0  # skip negative indices
        ]

        if not conditions:
            return chunks

        neighbor_result = await self.db.execute(
            select(DocumentChunk).where(or_(*conditions))
        )
        all_neighbors = list(neighbor_result.scalars().all())

        # Merge: original + neighbors, deduplicated
        merged: dict[uuid.UUID, DocumentChunk] = {}
        for chunk in chunks:
            merged[chunk.id] = chunk
        for chunk in all_neighbors:
            if chunk.id not in merged:
                merged[chunk.id] = chunk

        # Sort by document_id then chunk_index for coherent reading order
        result = sorted(
            merged.values(),
            key=lambda c: (
                str(c.document_id),
                c.chunk_index if c.chunk_index is not None else 0,
            ),
        )

        return result

    # ------------------------------------------------------------------
    # Build prompt
    # ------------------------------------------------------------------

    def build_prompt(
        self,
        system_prompt: str,
        context_chunks: list[DocumentChunk],
        history: list[Message],
        user_message: str,
        entity_context: str | None = None,
    ) -> list[dict]:
        """Build the message list for the LLM."""
        if context_chunks:
            # Build context with source labels including page metadata
            context_parts = []
            for i, chunk in enumerate(context_chunks):
                meta = chunk.metadata_ or {}
                page = meta.get("page_number")
                source_label = f"[Source {i+1}"
                if page:
                    source_label += f" | Page {page}"
                source_label += "]"
                context_parts.append(f"{source_label} {chunk.content}")

            context_text = "\n\n".join(context_parts)

            # Build entity context section if available
            entity_section = ""
            if entity_context:
                entity_section = f"\n\n{entity_context}\n"

            full_system = (
                f"{system_prompt}\n\n"
                "## RULES\n"
                "1. Answer using ONLY the document sources below.\n"
                "2. Read ALL sources before answering.\n"
                "3. CITE your sources: after each fact, add [Source N].\n"
                "4. If the answer is NOT found in any source, say: "
                "'This information is not available in the provided documents.'\n"
                "5. NEVER guess or invent information not in the sources.\n"
                "6. If page/chapter/section info is not in the source metadata, "
                "do NOT guess — omit it or say 'not specified'.\n"
                "7. Be COMPLETE for list queries — check every source "
                "and the entity index if provided.\n"
                "8. Be CONCISE — answer directly without unnecessary elaboration.\n"
                f"{entity_section}\n"
                f"## DOCUMENT SOURCES\n{context_text}"
            )
        else:
            full_system = (
                f"{system_prompt}\n\n"
                "No document context is available. Let the user know that no relevant "
                "documents were found and answer based on general knowledge if possible."
            )

        messages = [{"role": "system", "content": full_system}]

        # Add conversation history (trimmed to save context budget)
        for msg in history:
            content = msg.content
            if len(content) > HISTORY_MSG_MAX_CHARS:
                content = content[:HISTORY_MSG_MAX_CHARS] + "..."
            messages.append({"role": msg.role, "content": content})

        messages.append({"role": "user", "content": user_message})

        return messages

    # ------------------------------------------------------------------
    # Generate reply via Ollama
    # ------------------------------------------------------------------

    async def generate_reply(self, prompt: list[dict]) -> str:
        """Send prompt to Ollama LLM and return the assistant's reply."""
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
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
                return data.get("message", {}).get(
                    "content", "I could not generate a response."
                )
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

        query = (
            query.order_by(Conversation.created_at.desc()).limit(limit).offset(offset)
        )

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

    async def _get_bot(
        self, bot_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Bot:
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

    async def _get_document_for_chunk(
        self, document_id: uuid.UUID
    ) -> Document | None:
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()
