"""
Document Service - High-level document operations

Coordinates storage, parsing, chunking, and embedding services.
Used by both API endpoints and background workers.
"""
import logging
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import DocumentParserType, DocumentSourceType, DocumentStatus
from app.models import Bot, Document, DocumentBot, DocumentChunk, DocumentEntity
from app.schemas.document import DocumentListData
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
        parser_type: Optional[DocumentParserType] = None,
        bot_ids: Optional[list[uuid.UUID]] = None,
    ) -> Document:
        """
        Create a new document record, save the file, and link to bots.

        Args:
            name: Original filename
            file_content: Raw file bytes
            mime_type: MIME type
            organization_id: Organization that owns this document
            parser_type: Parser mode (simple/docling), uses default if None
            bot_ids: List of bot UUIDs to associate (optional, can be None/empty)

        Returns:
            Created Document instance with bots loaded
        """
        # 1. Save file to storage
        file_path = await self.storage.save(file_content, name, mime_type)

        # 2. Create document record
        document = Document(
            name=name,
            source_type=DocumentSourceType.FILE,
            file_path=file_path,
            file_size=len(file_content),
            mime_type=mime_type,
            parser_type=parser_type,
            organization_id=organization_id,
            status=DocumentStatus.PENDING,
        )

        self.db.add(document)
        await self.db.flush()

        # 3. Link bots via join table (if any bot_ids provided)
        if bot_ids:
            result = await self.db.execute(
                select(Bot.id).where(Bot.id.in_(bot_ids))
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
        Process a document: parse → chunk → embed → extract entities → store.

        Pipeline:
        1. Read file from storage
        2. Parse with page-level metadata
        3. Chunk with page tracking
        4. Embed all chunks
        5. Extract named entities (NER) from each chunk
        6. Save chunks + entities to DB
        """
        document = await self._get_document_or_none(document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")

        # Update status to processing
        document.status = DocumentStatus.PROCESSING
        await self.db.commit()

        try:
            # 1. Get file content
            file_content = await self.storage.get(document.file_path)

            # 2. Parse document (with page metadata)
            from app.services.parser import ParserService

            parser_type = document.parser_type or DocumentParserType(
                settings.DEFAULT_PARSER_TYPE
            )
            parser = ParserService(parser_type)
            parse_result = await parser.parse_with_metadata(
                file_content, document.mime_type, document.name
            )

            if not parse_result.full_text or not parse_result.full_text.strip():
                raise ValueError("No text extracted from document")

            # 3. Chunk text (page-aware if pages available)
            from app.services.chunker import ChunkerService

            chunker = ChunkerService()

            if parse_result.pages and any(p.page_number for p in parse_result.pages):
                # PDF with page numbers — use page-aware chunking
                chunks = chunker.chunk_pages(parse_result.pages, document.name)
            else:
                # Non-PDF or no page info — standard chunking
                chunks = chunker.chunk_with_sources(
                    parse_result.full_text, document.name
                )

            if not chunks:
                raise ValueError("No chunks created from document")

            logger.info(
                f"[PROCESS] Document {document_id}: {len(chunks)} chunks created"
            )

            # 4. Generate embeddings
            from app.services.embedding import EmbeddingService

            embedding_service = EmbeddingService()
            chunk_contents = [c["content"] for c in chunks]
            embeddings = await embedding_service.embed_batch(chunk_contents)

            logger.info(
                f"[PROCESS] Document {document_id}: embeddings generated"
            )

            # 5. Extract entities (NER) — fast, CPU-only, ~2-5s
            from app.services.entity_extractor import extract_entities_batch

            all_entities = extract_entities_batch(chunk_contents)

            logger.info(
                f"[PROCESS] Document {document_id}: entity extraction done"
            )

            # 6. Save chunks + entities to database
            saved_chunks: list[DocumentChunk] = []
            for chunk_data, emb in zip(chunks, embeddings):
                chunk_obj = DocumentChunk(
                    document_id=document.id,
                    content=chunk_data["content"],
                    metadata_=chunk_data["metadata"],
                    embedding=emb,
                    chunk_index=chunk_data["metadata"].get("chunk_index"),
                )
                self.db.add(chunk_obj)
                saved_chunks.append(chunk_obj)

            # Flush to get chunk IDs for entity foreign keys
            await self.db.flush()

            # Save entities
            entity_count = 0
            for chunk_obj, chunk_entities in zip(saved_chunks, all_entities):
                for ent in chunk_entities:
                    entity = DocumentEntity(
                        document_id=document.id,
                        chunk_id=chunk_obj.id,
                        entity_type=ent["type"],
                        entity_value=ent["value"],
                        count=ent["count"],
                        snippet=ent.get("snippet", "")[:500],
                    )
                    self.db.add(entity)
                    entity_count += 1

            # 7. Update document status
            document.status = DocumentStatus.READY
            document.chunk_count = len(chunks)
            document.error_message = None

            await self.db.commit()
            await self.db.refresh(document)

            logger.info(
                f"[PROCESS] Document {document_id}: READY. "
                f"{len(chunks)} chunks, {entity_count} entities"
            )

            return document

        except Exception as e:
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)[:1000]
            await self.db.commit()
            raise

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    async def _get_document_or_none(self, document_id: uuid.UUID) -> Document | None:
        """Get document by ID, returns None if not found. For worker context."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
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
        query = select(Document).where(Document.organization_id == organization_id)
        count_query = select(func.count()).select_from(Document).where(
            Document.organization_id == organization_id
        )

        if bot_id is not None:
            result = await self.db.execute(select(Bot).where(Bot.id == bot_id))
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Bot not found",
                )
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
    # DELETE
    # ------------------------------------------------------------------

    async def delete_document(
        self, document_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        """Delete document, its chunks, and join-table rows. Raises 404 if not found."""
        document = await self.get_document(document_id, organization_id)

        if document.file_path:
            await self.storage.delete(document.file_path)

        await self.db.delete(document)
        await self.db.commit()
