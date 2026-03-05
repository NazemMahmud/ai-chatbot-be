"""
Chat Service - RAG chat pipeline

Orchestrates: retrieve chunks → build prompt → generate reply → save messages
"""
import json
import logging
import re
import time
import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums.chat import MessageRole
from app.enums.document import DocumentStatus
from app.models import Bot, Conversation, Document, DocumentBot, DocumentChunk, Message
from app.schemas.chat import ChatResponse, SourceChunk
from app.services.bot import BotService
from app.services.embedding import EmbeddingService
from app.services.reranker import RerankerService

logger = logging.getLogger(__name__)

# Common filler/intent words to strip before embedding for better retrieval.
# These add "instructional" noise to the query vector without helping find content.
_FILLER_WORDS = frozenset({
    "tell", "me", "about", "explain", "describe", "what", "is", "are",
    "who", "how", "does", "do", "can", "you", "please", "give", "show",
    "find", "search", "look", "for", "the", "a", "an", "of", "in",
    "know", "want", "need", "would", "like", "could", "should",
})


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

        # 3. Build context-aware search query from conversation history
        history = await self._get_history(conversation.id, limit=10)
        search_message = await self._contextualize_query(message, history)

        # 4. Retrieve relevant chunks
        chunks = await self.retrieve_chunks(search_message, organization_id, bot_id)
        logger.info(f"[CHAT] Got {len(chunks)} chunks for bot={bot_id}, org={organization_id}")
        system_prompt = bot.system_prompt or settings.LLM_SYSTEM_PROMPT
        prompt = self.build_prompt(system_prompt, chunks, history, message)

        # 5. Generate reply
        t_llm = time.perf_counter()
        reply = await self.generate_reply(prompt)
        t_llm_ms = (time.perf_counter() - t_llm) * 1000
        logger.info(f"[CHAT] LLM response generated in {t_llm_ms:.0f}ms")

        # 5.5. Agentic RAG — retry with alternative queries if LLM refused
        if settings.AGENTIC_RAG_ENABLED and self._is_refusal_response(reply):
            logger.info("[AGENTIC] Refusal detected, generating retry queries...")
            retry_queries = await self._generate_retry_queries(message)
            seen_chunk_ids = {c.id for c in chunks}

            for attempt, retry_query in enumerate(
                retry_queries[:settings.AGENTIC_RAG_MAX_RETRIES], 1
            ):
                logger.info(f"[AGENTIC] Retry {attempt}/{settings.AGENTIC_RAG_MAX_RETRIES}: '{retry_query}'")
                retry_chunks = await self.retrieve_chunks(
                    retry_query, organization_id, bot_id
                )

                # Filter out already-seen chunks
                new_chunks = [c for c in retry_chunks if c.id not in seen_chunk_ids]
                if not new_chunks:
                    logger.info(f"[AGENTIC] Retry {attempt}: no new chunks found, skipping")
                    continue

                # Merge new chunks with existing, deduplicated
                seen_chunk_ids.update(c.id for c in new_chunks)
                all_chunks = chunks + new_chunks

                # Trim to context budget
                trimmed: list[DocumentChunk] = []
                char_count = 0
                for c in all_chunks:
                    if char_count + len(c.content) > self.MAX_CONTEXT_CHARS:
                        break
                    trimmed.append(c)
                    char_count += len(c.content)

                # Re-generate with merged context but ORIGINAL user message
                retry_prompt = self.build_prompt(
                    system_prompt, trimmed, history, message
                )
                retry_reply = await self.generate_reply(retry_prompt)

                if not self._is_refusal_response(retry_reply):
                    logger.info(f"[AGENTIC] Retry {attempt} succeeded — got a real answer")
                    reply = retry_reply
                    chunks = trimmed
                    break
                else:
                    logger.info(f"[AGENTIC] Retry {attempt} still refused")
            else:
                logger.info("[AGENTIC] All retries exhausted, returning original response")

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
    # RAG: Retrieve chunks (Hybrid: Vector + Keyword + RRF)
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

    @staticmethod
    def _extract_search_query(raw_query: str) -> str:
        """
        Strip filler/intent words from user query to get the core search terms.

        "tell me about moon mother" → "moon mother"
        "what is the spiral symbol"  → "spiral symbol"
        "who is Madame Pailin"       → "Madame Pailin"

        If stripping leaves nothing (e.g. "tell me"), fall back to raw query.
        """
        words = raw_query.strip().split()
        core = [w for w in words if w.lower() not in _FILLER_WORDS]
        result = " ".join(core).strip()
        if not result:
            return raw_query.strip()
        logger.info(f"[RAG] Query: '{raw_query.strip()}' → search terms: '{result}'")
        return result

    # ------------------------------------------------------------------
    # Conversation-aware query (resolve follow-up references)
    # ------------------------------------------------------------------

    _CONTEXTUALIZE_PROMPT = (
        "Given the conversation history and the latest user question, "
        "rewrite the question as a standalone search query that includes "
        "all necessary context. If the question is already self-contained, "
        "return it unchanged.\n\n"
        "Conversation:\n{history}\n\n"
        "Latest question: {question}\n\n"
        "Return ONLY the rewritten search query, nothing else."
    )

    async def _contextualize_query(
        self, message: str, history: list,
    ) -> str:
        """
        Use conversation history to resolve follow-up references.

        "with whom moon mother interacted first?" + history about Moon Mother
        → "who did the Moon Mother interact with first in the story"

        Skips LLM call if no history (first message in conversation).
        Falls back to original message on any failure.
        """
        if not history:
            return message

        # Build a compact conversation summary for the LLM
        history_lines = []
        for msg in history[-6:]:  # last 6 messages (3 turns) for context
            role = "User" if msg.role == "user" else "Assistant"
            content = msg.content[:200]  # keep compact
            history_lines.append(f"{role}: {content}")

        history_text = "\n".join(history_lines)
        prompt = self._CONTEXTUALIZE_PROMPT.format(
            history=history_text, question=message,
        )

        model = settings.OLLAMA_SUMMARY_MODEL or settings.OLLAMA_LLM_MODEL

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You rewrite follow-up questions into standalone search queries. Return only the query.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                rewritten = data.get("message", {}).get("content", "").strip()

                # Sanity check: not empty, not too long, not a refusal
                if rewritten and len(rewritten) < 500:
                    logger.info(
                        f"[RAG] Contextualized query: '{message}' → '{rewritten}'"
                    )
                    return rewritten

        except Exception as e:
            logger.warning(f"[RAG] Query contextualization failed: {e}")

        return message

    # ------------------------------------------------------------------
    # Query Rewriting (Feature: multi-query retrieval)
    # ------------------------------------------------------------------

    _QUERY_REWRITE_PROMPT = (
        "Given this user question, generate {num_queries} different search queries "
        "that would help find relevant information in a document database.\n"
        "Each query should approach the topic from a different angle — "
        "use synonyms, related concepts, or different phrasings.\n"
        "Return ONLY a JSON array of strings, nothing else.\n\n"
        "Question: {query}"
    )

    async def _rewrite_queries(self, query: str) -> list[str]:
        """
        Use the LLM to generate alternative search queries for multi-query retrieval.

        Returns a list of rewritten queries. Always includes the original query.
        Falls back to [query] on any failure.
        """
        if not settings.QUERY_REWRITE_ENABLED:
            return [query]

        model = settings.OLLAMA_SUMMARY_MODEL or settings.OLLAMA_LLM_MODEL
        prompt = self._QUERY_REWRITE_PROMPT.format(
            num_queries=settings.QUERY_REWRITE_NUM_QUERIES,
            query=query,
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You generate search queries. Return only a JSON array of strings.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                raw = data.get("message", {}).get("content", "").strip()

                # Strip markdown code fences if present
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

                queries = json.loads(raw)
                if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                    # Always include the original query first
                    result = [query] + [q for q in queries if q.strip() and q != query]
                    logger.info(f"[RAG] Query rewrite: {len(result)} queries generated")
                    return result

        except Exception as e:
            logger.warning(f"[RAG] Query rewrite failed, using original: {e}")

        return [query]

    # ------------------------------------------------------------------
    # Metadata search (Feature: JSONB metadata-aware retrieval)
    # ------------------------------------------------------------------

    async def _metadata_search(
        self, query: str, doc_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """
        Search chunks by JSONB metadata (entities, key_terms).

        Extracts key terms from the user query and searches the metadata_ JSONB
        column using PostgreSQL array containment (?| operator).
        Uses the GIN index on metadata for fast lookups.
        """
        if not settings.METADATA_EXTRACTION_ENABLED:
            return []

        # Extract search terms from the query
        search_terms = self._extract_search_query(query).lower().split()
        if not search_terms:
            return []

        try:
            # Use raw SQL for JSONB array search with ?| operator
            # This checks if any of the search terms appear in entities or key_terms arrays
            from sqlalchemy import text, bindparam
            from sqlalchemy.dialects.postgresql import ARRAY
            from sqlalchemy import String

            # Build a query that checks both entities and key_terms arrays
            # Using jsonb_array_elements_text to unnest and compare
            stmt = text("""
                SELECT DISTINCT dc.id
                FROM document_chunks dc,
                     LATERAL jsonb_array_elements_text(
                         COALESCE(dc.metadata->'entities', '[]'::jsonb)
                         || COALESCE(dc.metadata->'key_terms', '[]'::jsonb)
                     ) AS term
                WHERE dc.document_id = ANY(:doc_ids)
                  AND dc.deleted_at IS NULL
                  AND LOWER(term) LIKE ANY(:patterns)
                LIMIT :limit
            """)

            # Create LIKE patterns for partial matching
            patterns = [f"%{t}%" for t in search_terms]

            result = await self.db.execute(
                stmt,
                {
                    "doc_ids": [str(d) for d in doc_ids],
                    "patterns": patterns,
                    "limit": settings.KEYWORD_TOP_K,
                },
            )
            ids = [row[0] for row in result.all()]
            logger.info(f"[RAG] Metadata search found {len(ids)} chunks for terms={search_terms}")
            return ids

        except Exception as e:
            logger.warning(f"[RAG] Metadata search failed: {e}")
            return []

    async def retrieve_chunks(
        self, query: str, organization_id: uuid.UUID, bot_id: uuid.UUID | None = None,
    ) -> list[DocumentChunk]:
        """
        Hybrid retrieval with bot-scoped access:
        1. Extract core search terms from user query
        2. Determine doc scope (bot-linked or all org docs)
        3. If small dataset → return all chunks
        4. If large dataset → vector search + keyword search → RRF merge → neighbor expansion
        """
        logger.info(f"[RAG] retrieve_chunks called for org={organization_id}, bot={bot_id}")

        # Extract core search terms (strip filler words)
        search_query = self._extract_search_query(query)

        try:
            query_embedding = await self.embedding_service.embed(search_query)
            logger.info(f"[RAG] Query embedded OK, vector length={len(query_embedding)}")
        except Exception as e:
            logger.error(f"[RAG] Embedding FAILED: {e}")
            return []

        # Determine which documents to search
        doc_ids = await self._get_scoped_doc_ids(organization_id, bot_id)

        if not doc_ids:
            logger.warning(f"[RAG] No ready documents found for org {organization_id}")
            return []

        # Count total chunks
        count_result = await self.db.execute(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id.in_(doc_ids),
                DocumentChunk.deleted_at.is_(None),
            )
        )
        total_chunks = count_result.scalar() or 0
        max_chunks = self.MAX_CONTEXT_CHARS // settings.CHUNK_SIZE
        logger.info(f"[RAG] total_chunks={total_chunks}, max_chunks={max_chunks}")

        if total_chunks <= max_chunks:
            # Small dataset: send ALL chunks ordered by relevance
            stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id.in_(doc_ids),
                    DocumentChunk.deleted_at.is_(None),
                )
                .order_by(
                    DocumentChunk.embedding.cosine_distance(query_embedding)
                )
            )
            logger.info(f"[RAG] Small dataset ({total_chunks} chunks) — sending all")
            try:
                result = await self.db.execute(stmt)
                chunks = list(result.scalars().all())
                logger.info(f"[RAG] Retrieved all {len(chunks)} chunks")
                return chunks
            except Exception as e:
                logger.error(f"[RAG] Chunk query FAILED: {e}")
                return []

        # ------------------------------------------------------------------
        # Large dataset: Hybrid retrieval
        # ------------------------------------------------------------------
        t_start = time.perf_counter()
        logger.info(f"[RAG] Large dataset ({total_chunks} chunks) — hybrid retrieval")

        # Step 1: Multi-query vector search
        # If query rewriting is enabled, generate alternative queries and
        # run vector search for each. Otherwise, single query as before.
        rewritten_queries = await self._rewrite_queries(search_query)

        all_vector_lists: list[list[uuid.UUID]] = []
        for rq in rewritten_queries:
            try:
                rq_embedding = await self.embedding_service.embed(rq)
                v_ids = await self._vector_search(rq_embedding, doc_ids)
                all_vector_lists.append(v_ids)
            except Exception as e:
                logger.warning(f"[RAG] Vector search failed for rewritten query '{rq}': {e}")

        # Merge all vector results via RRF (if multiple queries)
        if len(all_vector_lists) > 1:
            vector_ids = self._rrf_merge(*all_vector_lists)
        elif all_vector_lists:
            vector_ids = all_vector_lists[0]
        else:
            vector_ids = []

        # Step 2: Keyword search — top K by tsvector match
        keyword_ids = await self._keyword_search(search_query, doc_ids)

        # Step 3: Metadata search — JSONB entities/key_terms (if metadata extraction enabled)
        metadata_ids = await self._metadata_search(search_query, doc_ids)

        # Step 4: RRF merge (vector + keyword + metadata)
        merged_ids = self._rrf_merge(vector_ids, keyword_ids, metadata_ids)

        # Step 5: Rerank (cross-encoder) — scores each candidate against the query
        if settings.RERANKER_ENABLED and merged_ids:
            reranked_ids = await self._rerank(query, merged_ids)
        else:
            reranked_ids = merged_ids[:max_chunks]

        # Step 6: Neighbor expansion (chunk_index ± 1)
        neighbor_ids = await self._expand_neighbors(reranked_ids, doc_ids)

        # Step 7: Fetch full chunk objects, deduplicated
        all_ids = list(dict.fromkeys(reranked_ids + neighbor_ids))
        chunks = await self._fetch_chunks_by_ids(all_ids)

        # Sort by (document_id, chunk_index) for reading order
        chunks.sort(key=lambda c: (str(c.document_id), c.chunk_index or 0))

        # Trim to MAX_CONTEXT_CHARS
        final: list[DocumentChunk] = []
        char_count = 0
        for chunk in chunks:
            if char_count + len(chunk.content) > self.MAX_CONTEXT_CHARS:
                break
            final.append(chunk)
            char_count += len(chunk.content)

        t_elapsed = (time.perf_counter() - t_start) * 1000
        # Observability: structured retrieval log
        logger.info(
            "[RAG] retrieval_complete | "
            f"queries={len(rewritten_queries)} "
            f"vector={len(vector_ids)} keyword={len(keyword_ids)} "
            f"metadata={len(metadata_ids)} "
            f"rrf={len(merged_ids)} reranked={len(reranked_ids)} "
            f"neighbors={len(neighbor_ids)} final={len(final)} "
            f"chars={char_count} time_ms={t_elapsed:.0f}"
        )
        return final

    # ------------------------------------------------------------------
    # Hybrid retrieval helpers
    # ------------------------------------------------------------------

    async def _get_scoped_doc_ids(
        self, organization_id: uuid.UUID, bot_id: uuid.UUID | None,
    ) -> list[uuid.UUID]:
        """Get document IDs scoped to bot (if linked) or all org docs."""
        doc_ids: list[uuid.UUID] = []

        if bot_id:
            linked_result = await self.db.execute(
                select(DocumentBot.document_id).where(DocumentBot.bot_id == bot_id)
            )
            linked_doc_ids = [row[0] for row in linked_result.all()]

            if linked_doc_ids:
                doc_ids_result = await self.db.execute(
                    select(Document.id).where(
                        Document.id.in_(linked_doc_ids),
                        Document.organization_id == organization_id,
                        Document.status == DocumentStatus.READY,
                        Document.deleted_at.is_(None),
                    )
                )
                doc_ids = [row[0] for row in doc_ids_result.all()]
                logger.info(
                    f"[RAG] Bot has {len(linked_doc_ids)} linked docs, {len(doc_ids)} ready"
                )

        # Fallback: no bot_id or bot has no linked docs
        if not doc_ids:
            doc_ids_result = await self.db.execute(
                select(Document.id).where(
                    Document.organization_id == organization_id,
                    Document.status == DocumentStatus.READY,
                    Document.deleted_at.is_(None),
                )
            )
            doc_ids = [row[0] for row in doc_ids_result.all()]
            logger.info(f"[RAG] Fallback to all org docs: {len(doc_ids)} ready documents")

        return doc_ids

    async def _vector_search(
        self, query_embedding: list[float], doc_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Return chunk IDs ranked by cosine similarity (closest first)."""
        stmt = (
            select(DocumentChunk.id)
            .where(
                DocumentChunk.document_id.in_(doc_ids),
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
            .limit(settings.VECTOR_TOP_K)
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def _keyword_search(
        self, query: str, doc_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """
        Return chunk IDs ranked by tsvector keyword match.

        Uses websearch_to_tsquery with a phrase-first strategy:
          - Exact phrase match (quoted) is tried first and ranked highest
          - Individual words joined with OR catch partial matches
          - ts_rank naturally scores chunks matching the full phrase higher

        Example: "moon mother" →
          '"moon mother" OR moon OR mother'
          Chunks with "Moon Mother" rank top, "moon" alone ranks lower.
        """
        words = query.strip().split()

        # Build: "full phrase" OR word1 OR word2 ...
        parts = []
        if len(words) > 1:
            parts.append(f'"{query.strip()}"')  # exact phrase (highest rank)
        parts.extend(words)                      # individual words (fallback)
        or_query = " OR ".join(parts)

        ts_query = func.websearch_to_tsquery("english", or_query)

        stmt = (
            select(DocumentChunk.id)
            .where(
                DocumentChunk.document_id.in_(doc_ids),
                DocumentChunk.search_vector.op("@@")(ts_query),
                DocumentChunk.deleted_at.is_(None),
            )
            .order_by(func.ts_rank(DocumentChunk.search_vector, ts_query).desc())
            .limit(settings.KEYWORD_TOP_K)
        )
        try:
            result = await self.db.execute(stmt)
            return [row[0] for row in result.all()]
        except Exception as e:
            logger.error(f"[RAG] Keyword search FAILED: {e}")
            return []

    @staticmethod
    def _rrf_merge(
        *ranked_lists: list[uuid.UUID],
        k: int | None = None,
    ) -> list[uuid.UUID]:
        """
        Merge multiple ranked lists using Reciprocal Rank Fusion.

        Accepts any number of ranked ID lists. Each list contributes
        1/(k + rank + 1) to the score of each item.
        """
        if k is None:
            k = settings.RRF_K

        scores: dict[uuid.UUID, float] = {}

        for ranked_list in ranked_lists:
            for rank, chunk_id in enumerate(ranked_list):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)

        # Sort by RRF score descending (highest = most relevant)
        return sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

    async def _rerank(
        self, query: str, chunk_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Rerank candidates using cross-encoder for higher accuracy."""
        # Fetch chunk contents for the reranker
        chunks = await self._fetch_chunks_by_ids(chunk_ids)
        id_to_content = {c.id: c.content for c in chunks}

        # Maintain the RRF order for lookup
        ordered_ids = [cid for cid in chunk_ids if cid in id_to_content]
        ordered_contents = [id_to_content[cid] for cid in ordered_ids]

        return RerankerService.rerank(
            query=query,
            chunk_ids=ordered_ids,
            chunk_contents=ordered_contents,
            top_n=settings.RERANKER_TOP_N,
        )

    async def _expand_neighbors(
        self, chunk_ids: list[uuid.UUID], doc_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Fetch chunk_index ± 1 for context continuity."""
        if not chunk_ids:
            return []

        # Get (document_id, chunk_index) for selected chunks
        result = await self.db.execute(
            select(DocumentChunk.document_id, DocumentChunk.chunk_index)
            .where(
                DocumentChunk.id.in_(chunk_ids),
                DocumentChunk.deleted_at.is_(None),
            )
        )
        pairs = result.all()

        # Build set of neighbor (doc_id, chunk_index) pairs
        neighbor_pairs = set()
        for doc_id, idx in pairs:
            if idx is not None:
                neighbor_pairs.add((doc_id, idx - 1))
                neighbor_pairs.add((doc_id, idx + 1))

        if not neighbor_pairs:
            return []

        # Query neighbors not already in our set
        # Uses B-tree index on (document_id, chunk_index)
        try:
            neighbor_result = await self.db.execute(
                select(DocumentChunk.id).where(
                    tuple_(DocumentChunk.document_id, DocumentChunk.chunk_index).in_(
                        neighbor_pairs
                    ),
                    DocumentChunk.id.notin_(chunk_ids),
                    DocumentChunk.deleted_at.is_(None),
                )
            )
            return [row[0] for row in neighbor_result.all()]
        except Exception as e:
            logger.error(f"[RAG] Neighbor expansion FAILED: {e}")
            return []

    async def _fetch_chunks_by_ids(
        self, chunk_ids: list[uuid.UUID],
    ) -> list[DocumentChunk]:
        """Fetch full DocumentChunk objects by IDs."""
        if not chunk_ids:
            return []
        result = await self.db.execute(
            select(DocumentChunk).where(
                DocumentChunk.id.in_(chunk_ids),
                DocumentChunk.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

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
                "## CRITICAL RULES — YOU MUST FOLLOW THESE\n"
                "1. Answer using ONLY the document context below. "
                "You are FORBIDDEN from using your training data or general knowledge.\n"
                "2. Read EVERY source carefully from start to end before answering.\n"
                "3. Be COMPLETE — include ALL matching items from ALL sources. "
                "Do NOT stop early or skip any source.\n"
                "4. If asked whether something exists, search ALL sources "
                "before saying it does not exist.\n"
                "5. Be CONCISE — answer directly without unnecessary elaboration.\n"
                "6. If the context does NOT contain enough information to answer "
                "the question, you MUST respond EXACTLY with: "
                '"I don\'t have enough information about that in the uploaded documents."\n'
                "7. NEVER make up, invent, or fabricate ANY information. "
                "Do NOT fill gaps with outside knowledge. "
                "If the context mentions something briefly without detail, "
                "say only what the context says — nothing more.\n"
                "8. If you are unsure, say you are unsure. Never guess.\n\n"
                f"## DOCUMENT CONTEXT\n{context_text}"
            )
        else:
            full_system = (
                f"{system_prompt}\n\n"
                "No relevant documents were found for this question. "
                "You MUST respond with: "
                '"I don\'t have information about that in the uploaded documents." '
                "Do NOT attempt to answer from general knowledge. "
                "Do NOT make up any information."
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
            async with httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT) as client:
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
    # Agentic RAG (Feature: retry on refusal)
    # ------------------------------------------------------------------

    _REFUSAL_PATTERNS = [
        # Direct refusals
        "i don't have enough information",
        "i don't have information about that",
        "not mentioned in the",
        "not found in the",
        "no information about",
        "cannot find",
        "unable to find",
        "don't have any information",
        "no relevant information",
        "not covered in the",
        "not discussed in the",
        "in the uploaded documents",
        # Confused / asking for clarification (LLM lost context)
        "could you please provide more details",
        "could you please clarify",
        "which story",
        "which narrative",
        "which document",
        "are you referring to",
        "can you specify",
        "please provide more context",
        "i'm not sure which",
        "missing context",
        "need more context",
        "what are you referring to",
    ]

    @staticmethod
    def _is_refusal_response(reply: str) -> bool:
        """Check if the LLM response is a refusal (couldn't find info)."""
        reply_lower = reply.lower()
        return any(pattern in reply_lower for pattern in ChatService._REFUSAL_PATTERNS)

    _AGENTIC_RETRY_PROMPT = (
        "The user asked: \"{original_query}\"\n"
        "The system searched for information but couldn't find relevant results.\n\n"
        "Suggest {num_queries} alternative search queries that might find the answer. Try:\n"
        "- Different wording or synonyms\n"
        "- Broader or narrower scope\n"
        "- Related concepts or different angles\n\n"
        "Return ONLY a JSON array of strings, nothing else."
    )

    async def _generate_retry_queries(
        self, original_query: str, num_queries: int = 3,
    ) -> list[str]:
        """
        Ask the LLM to suggest alternative search queries when initial retrieval fails.

        Returns list of alternative queries. Empty list on failure.
        """
        model = settings.OLLAMA_SUMMARY_MODEL or settings.OLLAMA_LLM_MODEL
        prompt = self._AGENTIC_RETRY_PROMPT.format(
            original_query=original_query,
            num_queries=num_queries,
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You generate search queries. Return only a JSON array of strings.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                raw = data.get("message", {}).get("content", "").strip()

                # Strip markdown code fences
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

                queries = json.loads(raw)
                if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                    result = [q for q in queries if q.strip()]
                    logger.info(f"[AGENTIC] Generated {len(result)} retry queries")
                    return result

        except Exception as e:
            logger.warning(f"[AGENTIC] Retry query generation failed: {e}")

        return []

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
            Conversation.organization_id == organization_id,
            Conversation.deleted_at.is_(None),
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
        return await BotService(self.db).get_bot_or_raise(
            bot_id,
            organization_id=organization_id,
            require_active=True,
        )

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
                    Conversation.deleted_at.is_(None),
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
                Conversation.deleted_at.is_(None),
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
            select(Document).where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
