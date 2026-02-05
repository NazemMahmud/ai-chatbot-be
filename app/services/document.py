"""
Document Service - High-level document operations

Coordinates storage, parsing, chunking, and embedding services.
Used by both API endpoints and background workers.
"""
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import DocumentParserType, DocumentSourceType, DocumentStatus
from app.models import Bot, Document, DocumentBot, DocumentChunk
from app.schemas.document import DocumentListData
from app.services.storage import get_storage_service


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
        parser_type: Optional[DocumentParserType] = None,
        bot_ids: Optional[list[uuid.UUID]] = None,
    ) -> Document:
        """
        Create a new document record, save the file, and link to bots.

        Args:
            name: Original filename
            file_content: Raw file bytes
            mime_type: MIME type
            parser_type: Parser mode (simple/docling), uses default if None
            bot_ids: List of bot UUIDs to associate (optional, can be None/empty)

        Returns:
            Created Document instance with bots loaded
        """
        # 1. Save file to storage
        file_path = await self.storage.save(file_content, name, mime_type)

        # 2. Create document record (no bot_id column anymore)
        document = Document(
            name=name,
            source_type=DocumentSourceType.FILE,
            file_path=file_path,
            file_size=len(file_content),
            mime_type=mime_type,
            parser_type=parser_type,
            status=DocumentStatus.PENDING,
        )

        self.db.add(document)
        await self.db.flush()  # assigns document.id without committing

        # 3. Link bots via join table (if any bot_ids provided)
        if bot_ids:
            # Validate all bot IDs exist in a single query
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

        await self.db.commit()
        await self.db.refresh(document)

        return document

    # ------------------------------------------------------------------
    # PROCESS (called by worker)
    # ------------------------------------------------------------------

    async def process_document(self, document_id: uuid.UUID) -> Document:
        """
        Process a document: parse → chunk → embed → store.

        This is the main processing pipeline called by the background worker.
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

            # 2. Parse document
            from app.services.parser import ParserService

            parser_type = document.parser_type or DocumentParserType(
                settings.DEFAULT_PARSER_TYPE
            )
            parser = ParserService(parser_type)
            text = await parser.parse(file_content, document.mime_type, document.name)

            if not text or not text.strip():
                raise ValueError("No text extracted from document")

            # 3. Chunk text
            from app.services.chunker import ChunkerService

            chunker = ChunkerService()
            chunks = chunker.chunk_with_sources(text, document.name)

            if not chunks:
                raise ValueError("No chunks created from document")

            # 4. Generate embeddings
            from app.services.embedding import EmbeddingService

            embedding_service = EmbeddingService()
            chunk_contents = [c["content"] for c in chunks]
            embeddings = await embedding_service.embed_batch(chunk_contents)

            # 5. Save chunks to database
            for chunk_data, emb in zip(chunks, embeddings):
                chunk = DocumentChunk(
                    document_id=document.id,
                    content=chunk_data["content"],
                    metadata_=chunk_data["metadata"],
                    embedding=emb,
                )
                self.db.add(chunk)

            # 6. Update document status
            document.status = DocumentStatus.READY
            document.chunk_count = len(chunks)
            document.error_message = None

            await self.db.commit()
            await self.db.refresh(document)

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

    async def get_document(self, document_id: uuid.UUID) -> Document:
        """Get document by ID or raise 404."""
        document = await self._get_document_or_none(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        return document

    async def list_documents(
        self,
        bot_id: Optional[uuid.UUID] = None,
        doc_status: Optional[DocumentStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> DocumentListData:
        """List documents with optional bot_id and status filters, paginated."""
        query = select(Document)
        count_query = select(func.count()).select_from(Document)

        if bot_id is not None:
            # Validate bot exists
            bot_result = await self.db.execute(select(Bot).where(Bot.id == bot_id))
            if not bot_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Bot not found",
                )
            # Filter via the join table
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

    async def delete_document(self, document_id: uuid.UUID) -> None:
        """Delete document, its chunks, and join-table rows. Raises 404 if not found."""
        document = await self.get_document(document_id)

        # Delete file from storage
        if document.file_path:
            await self.storage.delete(document.file_path)

        # Delete document (cascades to chunks + document_bots via ON DELETE CASCADE)
        await self.db.delete(document)
        await self.db.commit()
