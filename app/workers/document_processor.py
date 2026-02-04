"""
Document processing pipeline — called by ARQ background worker.

Flow: download file -> parse (simple or docling) -> chunk -> embed -> store in pgvector
Status transitions: pending -> processing -> ready | failed
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.services.embedding import EmbeddingService
from app.utils.chunking import chunk_text
from app.utils.parsers import parse_document
from app.utils.scraper import scrape_url


class DocumentProcessor:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_service = EmbeddingService()

    async def process(self, document_id: str):
        """Process an uploaded document end-to-end."""
        doc = await self._get_document(document_id)
        if not doc:
            return

        await self._update_status(doc, "processing")

        try:
            # 1. Download file from storage
            # TODO: download from MinIO using doc.file_path
            file_path = doc.file_path  # placeholder — use local path for now

            # 2. Parse based on parser_type (simple or docling)
            text = parse_document(
                file_path=file_path,
                mime_type=doc.mime_type or "text/plain",
                parser_type=doc.parser_type,
            )

            # 3. Chunk the text
            chunks = chunk_text(
                text=text,
                chunk_size=512,
                chunk_overlap=50,
                metadata={"document_id": str(doc.id), "source": doc.name},
            )

            if not chunks:
                await self._update_status(doc, "failed", error="No text content extracted")
                return

            # 4. Generate embeddings (batch)
            texts = [c.text for c in chunks]
            embeddings = await self.embedding_service.generate_embeddings(texts)

            # 5. Store chunks + embeddings in pgvector
            for chunk, embedding in zip(chunks, embeddings):
                db_chunk = DocumentChunk(
                    document_id=doc.id,
                    bot_id=doc.bot_id,
                    content=chunk.text,
                    metadata_=chunk.metadata,
                    embedding=embedding,
                )
                self.db.add(db_chunk)

            # 6. Update status
            await self._update_status(doc, "ready", chunk_count=len(chunks))

        except Exception as e:
            await self._update_status(doc, "failed", error=str(e))
            raise

    async def process_url(self, document_id: str, url: str):
        """Process a URL: scrape -> chunk -> embed -> store."""
        doc = await self._get_document(document_id)
        if not doc:
            return

        await self._update_status(doc, "processing")

        try:
            # 1. Scrape URL
            text = await scrape_url(url)

            # 2. Chunk
            chunks = chunk_text(
                text=text,
                chunk_size=512,
                chunk_overlap=50,
                metadata={"document_id": str(doc.id), "source": url},
            )

            if not chunks:
                await self._update_status(doc, "failed", error="No text content extracted from URL")
                return

            # 3. Embed
            texts = [c.text for c in chunks]
            embeddings = await self.embedding_service.generate_embeddings(texts)

            # 4. Store
            for chunk, embedding in zip(chunks, embeddings):
                db_chunk = DocumentChunk(
                    document_id=doc.id,
                    bot_id=doc.bot_id,
                    content=chunk.text,
                    metadata_=chunk.metadata,
                    embedding=embedding,
                )
                self.db.add(db_chunk)

            await self._update_status(doc, "ready", chunk_count=len(chunks))

        except Exception as e:
            await self._update_status(doc, "failed", error=str(e))
            raise

    async def _get_document(self, document_id: str) -> Document | None:
        result = await self.db.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
        return result.scalar_one_or_none()

    async def _update_status(
        self,
        doc: Document,
        status: str,
        chunk_count: int | None = None,
        error: str | None = None,
    ):
        doc.status = status
        if chunk_count is not None:
            doc.chunk_count = chunk_count
        if error is not None:
            doc.error_message = error
        await self.db.flush()
