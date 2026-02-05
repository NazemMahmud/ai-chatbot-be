"""
Document Processing Worker - ARQ background job handler

Handles async document processing: parse → chunk → embed → store
"""
import logging
import uuid
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.database import async_session
from app.services.document import DocumentService

logger = logging.getLogger(__name__)


async def process_document_job(ctx: dict, document_id: str) -> dict[str, Any]:
    """
    Background job to process a document.

    Args:
        ctx: ARQ context (contains redis connection, job info)
        document_id: UUID of the document to process

    Returns:
        Dict with processing result
    """
    doc_uuid = uuid.UUID(document_id)
    logger.info(f"Starting document processing: {document_id}")

    async with async_session() as db:
        service = DocumentService(db)

        try:
            document = await service.process_document(doc_uuid)
            logger.info(
                f"Document processed successfully: {document_id}, "
                f"chunks={document.chunk_count}"
            )
            return {
                "status": "success",
                "document_id": document_id,
                "chunk_count": document.chunk_count,
            }

        except Exception as e:
            logger.error(f"Document processing failed: {document_id}, error={e}")
            return {
                "status": "failed",
                "document_id": document_id,
                "error": str(e),
            }


async def startup(ctx: dict) -> None:
    """Called when worker starts."""
    logger.info("Document worker starting...")


async def shutdown(ctx: dict) -> None:
    """Called when worker shuts down."""
    logger.info("Document worker shutting down...")


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [process_document_job]

    on_startup = startup
    on_shutdown = shutdown

    # Redis connection
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

    # Worker settings
    max_jobs = settings.WORKER_MAX_JOBS
    job_timeout = settings.WORKER_JOB_TIMEOUT

    # Retry settings
    max_tries = 3
    retry_jobs = True

    # Queue name
    queue_name = "document_queue"

    # Health check
    health_check_interval = 30
