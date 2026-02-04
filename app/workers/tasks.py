"""
ARQ background worker tasks.

Run the worker with:
    arq app.workers.tasks.WorkerSettings
"""

from arq.connections import RedisSettings

from app.config import settings


async def process_document_task(ctx: dict, document_id: str):
    """
    Background job: process an uploaded document.
    Flow: download file -> detect type -> parse -> chunk -> embed -> store in pgvector
    """
    from app.database import async_session
    from app.workers.document_processor import DocumentProcessor

    async with async_session() as db:
        processor = DocumentProcessor(db)
        await processor.process(document_id)
        await db.commit()


async def scrape_url_task(ctx: dict, bot_id: str, url: str, document_id: str):
    """
    Background job: scrape a URL and process the content.
    Flow: fetch URL -> extract text -> chunk -> embed -> store
    """
    from app.database import async_session
    from app.workers.document_processor import DocumentProcessor

    async with async_session() as db:
        processor = DocumentProcessor(db)
        await processor.process_url(document_id, url)
        await db.commit()


async def sync_database_task(ctx: dict, db_connection_id: str, bot_id: str):
    """
    Background job: sync an external DB schema + sample data into vector store.
    """
    # TODO: implement via DBConnector.sync_to_chunks()
    pass


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [process_document_task, scrape_url_task, sync_database_task]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 300  # 5 minutes
