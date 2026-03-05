"""
Document Service - High-level document operations

Coordinates storage, parsing, chunking, and embedding services.
Used by both API endpoints and background workers.
"""
import json
import logging
import re
import uuid
from typing import Optional

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import DocumentParserType, DocumentSourceType, DocumentStatus
from app.models import Bot, Document, DocumentBot, DocumentChunk
from app.schemas.document import DocumentListData
from app.services.bot import BotService
from app.services.chunker import CharacterChunkerService, SemanticChunkerService
from app.services.embedding import EmbeddingService
from app.services.parser import ParserService
from app.services.storage import get_storage_service

logger = logging.getLogger(__name__)


class DocumentService:
    """High-level document operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage_service()

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    async def create_document(
        self,
        name: str,
        file_content: bytes,
        mime_type: str,
        organization_id: uuid.UUID,
        bot_ids: Optional[list[uuid.UUID]] = None,
    ) -> Document:
        """
        Create a new document record, save the file, and link to bots.

        Parser type is auto-detected during processing based on MIME type.

        Args:
            name: Original filename
            file_content: Raw file bytes
            mime_type: MIME type
            organization_id: Organization that owns this document
            bot_ids: List of bot UUIDs to associate (optional, can be None/empty)

        Returns:
            Created Document instance with bots loaded
        """
        # 1. Save file to storage
        file_path = await self.storage.save(file_content, name, mime_type)

        # 2. Create document record (parser_type is set during processing)
        document = Document(
            name=name,
            source_type=DocumentSourceType.FILE,
            file_path=file_path,
            file_size=len(file_content),
            mime_type=mime_type,
            organization_id=organization_id,
            status=DocumentStatus.PENDING,
        )

        self.db.add(document)
        await self.db.flush()

        # 3. Link bots via join table (if any bot_ids provided)
        if bot_ids:
            result = await self.db.execute(
                select(Bot.id).where(
                    Bot.id.in_(bot_ids),
                    Bot.deleted_at.is_(None),
                )
            )
            found_ids = {row[0] for row in result.all()}
            missing = set(bot_ids) - found_ids
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Bot(s) not found: {[str(m) for m in missing]}",
                )

            for bid in bot_ids:
                self.db.add(DocumentBot(document_id=document.id, bot_id=bid))

        await self.db.flush()
        await self.db.refresh(document)

        return document

    # ------------------------------------------------------------------
    # PROCESS (called by worker — no org scoping needed)
    # ------------------------------------------------------------------

    async def process_document(self, document_id: uuid.UUID) -> Document:
        """
        Process a document: parse → chunk → embed → store.

        This is the main processing pipeline called by the background worker.
        Chunking strategy is chosen from settings.CHUNKING_STRATEGY:
          - "character": fast, splits by character count (basic)
          - "semantic":  embeds sentences to find topic boundaries (production)
        """
        document = await self._get_document_or_none(document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")

        document.status = DocumentStatus.PROCESSING
        await self.db.commit()

        try:
            # 1. Get file content
            file_content = await self.storage.get(document.file_path)

            # 2. Auto-detect parser and extract text
            text, parser_type = await self._auto_parse(
                file_content, document.mime_type, document.name
            )

            # Record which parser was actually used (audit trail)
            document.parser_type = parser_type

            if not text or not text.strip():
                raise ValueError("No text extracted from document")

            # 2.5. Analyze document and enhance bot system prompts if needed
            await self._analyze_and_enhance_bot_prompts(document, text)

            # 3. Chunk text (strategy from config)
            embedding_service = EmbeddingService()
            chunks = await self._chunk_text(text, document.name, embedding_service)

            if not chunks:
                raise ValueError("No chunks created from document")

            # 3.5. Extract metadata for each chunk (if enabled)
            chunks = await self._extract_metadata_for_chunks(chunks)

            # 4. Generate embeddings for final chunks
            chunk_contents = [c["content"] for c in chunks]
            embeddings = await embedding_service.embed_batch(chunk_contents)

            # 5. Save chunks to database
            for chunk_data, emb in zip(chunks, embeddings):
                chunk = DocumentChunk(
                    document_id=document.id,
                    content=chunk_data["content"],
                    metadata_=chunk_data["metadata"],
                    embedding=emb,
                    chunk_index=chunk_data["metadata"].get("chunk_index"),
                )
                self.db.add(chunk)

            # 6. Update document status
            document.status = DocumentStatus.READY
            document.chunk_count = len(chunks)
            document.error_message = None

            await self.db.commit()
            await self.db.refresh(document)

            logger.info(
                f"Document {document_id} processed: {len(chunks)} chunks "
                f"(strategy={settings.CHUNKING_STRATEGY})"
            )
            return document

        except Exception as e:
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)[:1000]
            await self.db.commit()
            raise

    async def _chunk_text(
        self, text: str, source_name: str, embedding_service
    ) -> list[dict]:
        """Choose chunking strategy based on settings."""
        strategy = settings.CHUNKING_STRATEGY.lower()

        if strategy == "semantic":
            chunker = SemanticChunkerService(embedding_service)
            return await chunker.chunk_with_sources(text, source_name)
        else:
            chunker = CharacterChunkerService()
            return chunker.chunk_with_sources(text, source_name)

    # ------------------------------------------------------------------
    # AUTO-DETECT PARSER
    # ------------------------------------------------------------------

    _IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

    # Minimum chars from simple PDF parse to consider it a text PDF.
    # Below this threshold we assume it's a scanned PDF and retry with docling.
    _SCANNED_PDF_THRESHOLD = 50

    async def _auto_parse(
        self,
        file_content: bytes,
        mime_type: str,
        filename: str,
    ) -> tuple[str, DocumentParserType]:
        """
        Auto-detect the right parser and extract text.

        Strategy:
          - Images → docling (OCR required)
          - PDFs   → try simple first; if near-empty text, fallback to docling
          - Other  → simple

        Returns:
            (extracted_text, parser_type_used)
        """
        # Images always need OCR
        if mime_type in self._IMAGE_MIME_TYPES:
            logger.info(f"Image detected ({mime_type}), using docling parser")
            parser = ParserService(DocumentParserType.DOCLING)
            text = await parser.parse(file_content, mime_type, filename)
            return text, DocumentParserType.DOCLING

        # PDFs: try simple first, fallback to docling if scanned
        if mime_type == "application/pdf":
            parser = ParserService(DocumentParserType.SIMPLE)
            text = await parser.parse(file_content, mime_type, filename)

            if len(text.strip()) >= self._SCANNED_PDF_THRESHOLD:
                return text, DocumentParserType.SIMPLE

            # Likely a scanned PDF — fallback to docling for OCR
            logger.info(
                f"PDF yielded only {len(text.strip())} chars with simple parser, "
                f"retrying with docling (OCR)"
            )
            try:
                parser = ParserService(DocumentParserType.DOCLING)
                text = await parser.parse(file_content, mime_type, filename)
                return text, DocumentParserType.DOCLING
            except ImportError:
                logger.warning(
                    "Docling not installed — cannot OCR scanned PDF. "
                    "Install with: pip install docling"
                )
                # Return whatever simple got (may be empty)
                return text, DocumentParserType.SIMPLE

        # Everything else: simple parser
        parser = ParserService(DocumentParserType.SIMPLE)
        text = await parser.parse(file_content, mime_type, filename)
        return text, DocumentParserType.SIMPLE

    # ------------------------------------------------------------------
    # SMART SYSTEM PROMPT GENERATION
    # ------------------------------------------------------------------

    # Known default / placeholder system prompts — if the bot has one of
    # these (or is empty), we auto-generate a domain-specific prompt.
    _DEFAULT_SYSTEM_PROMPTS = {
        "You are a helpful assistant.",
        "You are a helpful AI assistant.",
        "You are a helpful AI assistant. Answer questions based on the provided context.",
    }

    _PROMPT_GENERATION_TEMPLATE = (
        "You are an AI assistant configuration expert. "
        "Generate a system prompt for an AI chatbot.\n\n"
        "## Bot Identity (HIGHEST PRIORITY — the prompt MUST match this)\n"
        "- Bot Name: {bot_name}\n"
        "- Bot Description: {bot_description}\n"
        "- Current System Prompt: {current_prompt}\n\n"
        "The bot name is the strongest signal about the bot's intended role. "
        "For example:\n"
        '- "Blog reader" → a reading companion / storyteller / content guide\n'
        '- "Legal advisor" → a legal assistant\n'
        '- "Product support" → a customer support agent\n\n'
        "## Document Sample (use as secondary context only)\n"
        "{document_sample}\n\n"
        "## Your Task\n"
        "1. Derive the bot's role primarily from its NAME and description.\n"
        "2. Use the document sample to add domain detail — but never let the "
        "document override the role implied by the bot name.\n"
        "3. If the bot name suggests a reader/storyteller (e.g., 'Blog reader', "
        "'Story bot') and the document is a story or novel, the prompt should "
        "reflect a storytelling or reading companion role — NOT a generic "
        "topic expert.\n\n"
        "Generate a professional system prompt that:\n"
        "- Starts with 'You are a [role matching the bot name]...'\n"
        "- Reflects the intent behind the bot name\n"
        "- Incorporates relevant details from the document as context\n"
        "- Sets the appropriate tone for that role\n\n"
        "Return ONLY the system prompt text. No explanations, no markdown "
        "formatting, no quotes around it. Just the prompt itself."
    )

    async def _analyze_and_enhance_bot_prompts(
        self, document: Document, full_text: str
    ) -> None:
        """
        Analyze document content and enhance linked bot system prompts.

        Only runs for bots with default/empty system prompts.
        Uses the LLM to generate a domain-specific system prompt.
        """
        if not document.bots:
            return

        # Take a representative sample of the document
        sample = full_text[:2000].strip()
        if not sample:
            return

        for bot in document.bots:
            # Skip if bot already has a custom system prompt
            current_prompt = (bot.system_prompt or "").strip()
            if current_prompt and current_prompt not in self._DEFAULT_SYSTEM_PROMPTS:
                logger.info(
                    f"Bot {bot.id} already has custom system prompt, "
                    f"skipping generation"
                )
                continue

            try:
                generated_prompt = await self._generate_system_prompt(
                    bot_name=bot.name,
                    bot_description=bot.description or "",
                    current_prompt=current_prompt,
                    document_sample=sample,
                )

                if generated_prompt and len(generated_prompt) > 20:
                    bot.system_prompt = generated_prompt
                    await self.db.flush()
                    logger.info(
                        f"Enhanced system prompt for bot {bot.id}: "
                        f"{generated_prompt[:100]}..."
                    )
            except Exception as e:
                # Smart prompt is a bonus — don't fail the pipeline
                logger.warning(
                    f"System prompt generation failed for bot {bot.id}: {e}"
                )

    async def _generate_system_prompt(
        self,
        bot_name: str,
        bot_description: str,
        current_prompt: str,
        document_sample: str,
    ) -> str | None:
        """Call Ollama LLM to generate a system prompt based on document analysis."""
        prompt = self._PROMPT_GENERATION_TEMPLATE.format(
            bot_name=bot_name,
            bot_description=bot_description or "Not provided",
            current_prompt=current_prompt or "Not set",
            document_sample=document_sample,
        )

        model = settings.OLLAMA_SUMMARY_MODEL or settings.OLLAMA_LLM_MODEL

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are an AI configuration expert. "
                                    "Generate system prompts for chatbots."
                                ),
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.warning(f"System prompt generation LLM call failed: {e}")
            return None

    # ------------------------------------------------------------------
    # SUMMARY EXTRACTION
    # ------------------------------------------------------------------

    SUMMARY_PROMPT = (
        "Extract ALL key information from the text below. "
        "Be exhaustive and complete.\n\n"
        "Provide the following sections:\n"
        "## Names / Entities\n"
        "List EVERY person, company, product, service, or named entity.\n\n"
        "## Key Terms / Definitions\n"
        "List important terms, acronyms, or definitions.\n\n"
        "## Key Facts / Data Points\n"
        "List important facts, numbers, dates, rules, policies, "
        "questions and answers, or procedures.\n\n"
        "## Summary\n"
        "A brief overview of what this content is about.\n\n"
        "Be thorough. Include EVERY name and detail, even minor ones. "
        "Only include sections that have content.\n\n"
        "TEXT:\n{text}"
    )

    async def _generate_summary_chunk(
        self,
        document_id: uuid.UUID,
        chunk_contents: list[str],
        embedding_service,
    ) -> None:
        """
        Use the LLM to extract key entities from the document and store
        as a special summary chunk. This chunk gets priority in RAG retrieval.
        """
        try:
            # Combine chunks into batches that fit LLM context.
            # Process in batches of ~10K chars (~2500 tokens) to stay safe.
            batch_size_chars = 10000
            summaries = []

            current_batch = ""
            for content in chunk_contents:
                if len(current_batch) + len(content) > batch_size_chars:
                    # Process this batch
                    summary = await self._extract_summary(current_batch)
                    if summary:
                        summaries.append(summary)
                    current_batch = content
                else:
                    current_batch += "\n\n" + content

            # Process the last batch
            if current_batch.strip():
                summary = await self._extract_summary(current_batch)
                if summary:
                    summaries.append(summary)

            if not summaries:
                logger.warning(f"No summaries generated for document {document_id}")
                return

            # If multiple batch summaries, merge them into one final summary
            if len(summaries) > 1:
                merged_text = "\n\n".join(summaries)
                final_summary = await self._extract_summary(
                    merged_text,
                    prompt_override=(
                        "You are a document analyst. Below are partial summaries "
                        "extracted from different sections of a document. Merge them "
                        "into ONE comprehensive summary. Remove duplicates but keep "
                        "ALL unique names, places, topics, and facts.\n\n"
                        "PARTIAL SUMMARIES:\n{text}"
                    ),
                )
            else:
                final_summary = summaries[0]

            if not final_summary:
                return

            # Embed and save as a special summary chunk
            summary_embedding = await embedding_service.embed(final_summary)

            summary_chunk = DocumentChunk(
                document_id=document_id,
                content=final_summary,
                metadata_={"is_summary": True, "chunk_index": -1},
                embedding=summary_embedding,
            )
            self.db.add(summary_chunk)
            await self.db.flush()

            logger.info(
                f"Summary chunk created for document {document_id} "
                f"({len(final_summary)} chars)"
            )

        except Exception as e:
            # Summary is a bonus — don't fail the whole pipeline
            logger.error(f"Summary generation failed for {document_id}: {e}")

    async def _extract_summary(
        self, text: str, prompt_override: str | None = None
    ) -> str | None:
        """Call Ollama LLM to extract summary from text."""
        prompt = (prompt_override or self.SUMMARY_PROMPT).format(text=text)

        # Use a dedicated summary model if configured, otherwise fall back
        # to the chat LLM. Set OLLAMA_SUMMARY_MODEL=phi4-mini in .env
        # for faster processing while keeping phi4 for chat.
        model = settings.OLLAMA_SUMMARY_MODEL or settings.OLLAMA_LLM_MODEL

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "You extract key information from any given content."},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"Summary extraction LLM call failed: {e}")
            return None

    # ------------------------------------------------------------------
    # METADATA EXTRACTION (Feature: enriched JSONB metadata per chunk)
    # ------------------------------------------------------------------

    _METADATA_EXTRACTION_PROMPT = (
        "Analyze this text and extract metadata as JSON. "
        "Return ONLY valid JSON, no explanation or markdown.\n"
        "{\n"
        '  "entities": ["list of people, companies, products, places, characters mentioned"],\n'
        '  "key_terms": ["important terms, concepts, or topics in this text"],\n'
        '  "topic": "one-line description of what this chunk is about",\n'
        '  "section_title": "inferred section or chapter title if detectable, else null"\n'
        "}\n"
        "Only include fields that have content. If nothing is detected for a field, omit it.\n\n"
        "TEXT:\n{chunk_content}"
    )

    async def _extract_chunk_metadata(self, content: str) -> dict:
        """
        Use the LLM to extract structured metadata from a single chunk.

        Returns dict with optional keys: entities, key_terms, topic, section_title.
        Returns empty dict on any failure (never breaks the pipeline).
        """
        prompt = self._METADATA_EXTRACTION_PROMPT.format(chunk_content=content[:3000])
        model = settings.OLLAMA_SUMMARY_MODEL or settings.OLLAMA_LLM_MODEL

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You extract structured metadata from text. Return only valid JSON.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                raw = data.get("message", {}).get("content", "").strip()

                # Strip markdown code fences if present (```json ... ```)
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    return {}

                # Sanitize: keep only expected keys with correct types
                result = {}
                if isinstance(parsed.get("entities"), list):
                    result["entities"] = [str(e) for e in parsed["entities"] if e]
                if isinstance(parsed.get("key_terms"), list):
                    result["key_terms"] = [str(t) for t in parsed["key_terms"] if t]
                if isinstance(parsed.get("topic"), str) and parsed["topic"]:
                    result["topic"] = parsed["topic"]
                if isinstance(parsed.get("section_title"), str) and parsed["section_title"]:
                    result["section_title"] = parsed["section_title"]

                return result

        except (json.JSONDecodeError, httpx.HTTPError, Exception) as e:
            logger.warning(f"Metadata extraction failed for chunk: {e}")
            return {}

    async def _extract_metadata_for_chunks(
        self, chunks: list[dict]
    ) -> list[dict]:
        """
        Extract metadata for all chunks and merge into existing chunk metadata.

        Processes sequentially (LLM handles one request at a time on CPU).
        Failures for individual chunks are logged and skipped.
        """
        if not settings.METADATA_EXTRACTION_ENABLED:
            return chunks

        logger.info(f"[META] Starting metadata extraction for {len(chunks)} chunks")

        for i, chunk in enumerate(chunks):
            try:
                extracted = await self._extract_chunk_metadata(chunk["content"])
                if extracted:
                    # Merge into existing metadata (don't replace)
                    chunk["metadata"] = {**chunk.get("metadata", {}), **extracted}
                    logger.debug(
                        f"[META] Chunk {i}: extracted {list(extracted.keys())}"
                    )
            except Exception as e:
                logger.warning(f"[META] Chunk {i} metadata extraction failed: {e}")

        logger.info("[META] Metadata extraction complete")
        return chunks

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    async def _get_document_or_none(self, document_id: uuid.UUID) -> Document | None:
        """Get document by ID, returns None if not found. For worker context."""
        result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_document(
        self, document_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Document:
        """Get document by ID scoped to organization, or raise 404."""
        result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == organization_id,
                Document.deleted_at.is_(None),
            )
        )
        document = result.scalar_one_or_none()
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        return document

    async def list_documents(
        self,
        organization_id: uuid.UUID,
        bot_id: Optional[uuid.UUID] = None,
        doc_status: Optional[DocumentStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> DocumentListData:
        """List documents scoped to organization with optional filters."""
        query = select(Document).where(
            Document.organization_id == organization_id,
            Document.deleted_at.is_(None),
        )
        count_query = select(func.count()).select_from(Document).where(
            Document.organization_id == organization_id,
            Document.deleted_at.is_(None),
        )

        if bot_id is not None:
            await BotService(self.db).get_bot_or_raise(bot_id)
            query = query.where(
                Document.id.in_(
                    select(DocumentBot.document_id).where(DocumentBot.bot_id == bot_id)
                )
            )
            count_query = count_query.where(
                Document.id.in_(
                    select(DocumentBot.document_id).where(DocumentBot.bot_id == bot_id)
                )
            )

        if doc_status is not None:
            query = query.where(Document.status == doc_status)
            count_query = count_query.where(Document.status == doc_status)

        query = query.order_by(Document.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        documents = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar()

        return DocumentListData(documents=documents, total=total)

    # ------------------------------------------------------------------
    # UPDATE BOT ASSOCIATIONS
    # ------------------------------------------------------------------

    async def update_document_bots(
        self,
        document_id: uuid.UUID,
        organization_id: uuid.UUID,
        bot_ids: list[uuid.UUID],
    ) -> Document:
        """
        Replace all bot associations for a document.

        Args:
            document_id: The document to update
            organization_id: Organization scope
            bot_ids: New complete list of bot IDs (replaces existing)

        Steps:
            1. Validate all bot_ids exist and belong to the same org ( shift this to another method)
            2. Remove existing associations ( TODO: shift this to another method)
            3. Create new associations ( TODO: shift this to another method)
            4. Refresh the document 
            5. Return the updated document

        Returns:
            Updated Document instance with refreshed bots ( TODO: shift this to another method)
        """
        document = await self.get_document(document_id, organization_id)
        # TODO: shift this to another method
        result = await self.db.execute(
            select(Bot.id).where(
                Bot.id.in_(bot_ids),
                Bot.organization_id == organization_id,
                Bot.deleted_at.is_(None),
            )
        )
        found_ids = {row[0] for row in result.all()}
        missing = set(bot_ids) - found_ids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bot(s) not found: {[str(m) for m in missing]}",
            )
        #######

        existing = await self.db.execute(
            select(DocumentBot).where(DocumentBot.document_id == document_id)
        )
        for row in existing.scalars().all():
            await self.db.delete(row)

        # Create new associations
        for bid in bot_ids:
            self.db.add(DocumentBot(document_id=document_id, bot_id=bid))

        await self.db.flush()
        await self.db.refresh(document)

        return document

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    async def delete_document(
        self, document_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        """Delete document, its chunks, and join-table rows. Raises 404 if not found."""
        document = await self.get_document(document_id, organization_id)

        if document.file_path:
            await self.storage.delete(document.file_path)

        # Soft-delete the document
        document.soft_delete()

        # Also soft-delete all associated chunks
        result = await self.db.execute(
            select(DocumentChunk).where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.deleted_at.is_(None),
            )
        )
        for chunk in result.scalars().all():
            chunk.soft_delete()

        await self.db.commit()
