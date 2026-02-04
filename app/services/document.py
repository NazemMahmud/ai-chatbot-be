import uuid

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload_document(
        self,
        bot_id: uuid.UUID,
        user_id: uuid.UUID,
        file: UploadFile,
        parser_type: str | None = None,
    ) -> Document:
        """
        1. Save file to MinIO/S3
        2. Create document record with status=pending
        3. Enqueue ARQ background job
        4. Return document (202 Accepted)
        """
        # TODO: verify user has access to bot

        # TODO: upload file to MinIO
        file_path = f"documents/{bot_id}/{file.filename}"

        doc = Document(
            bot_id=bot_id,
            name=file.filename or "untitled",
            source_type="file",
            file_path=file_path,
            file_size=file.size,
            mime_type=file.content_type,
            status="pending",
            parser_type=parser_type,
        )
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)

        # TODO: enqueue ARQ job -> process_document_task(doc.id)
        # redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        # await redis.enqueue_job("process_document_task", str(doc.id))

        return doc

    async def ingest_url(
        self,
        bot_id: uuid.UUID,
        user_id: uuid.UUID,
        url: str,
        parser_type: str | None = None,
    ) -> Document:
        """Create a document record for URL scraping and enqueue processing."""
        doc = Document(
            bot_id=bot_id,
            name=url,
            source_type="url",
            source_url=url,
            status="pending",
            parser_type=parser_type,
        )
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)

        # TODO: enqueue ARQ job -> scrape_url_task(bot_id, url, doc.id)

        return doc

    async def list_documents(self, bot_id: uuid.UUID, user_id: uuid.UUID) -> list[Document]:
        # TODO: verify user has access to bot
        result = await self.db.execute(
            select(Document).where(Document.bot_id == bot_id).order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_document_status(
        self, doc_id: uuid.UUID, user_id: uuid.UUID
    ) -> Document | None:
        # TODO: verify user has access
        result = await self.db.execute(select(Document).where(Document.id == doc_id))
        return result.scalar_one_or_none()

    async def delete_document(self, doc_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        # TODO: verify user has access
        result = await self.db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return False

        # TODO: delete file from MinIO
        await self.db.delete(doc)
        await self.db.flush()
        return True
