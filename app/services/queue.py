"""
Queue Service - Enqueue background jobs

Uses ARQ (async Redis queue) for job management.
"""
import uuid
from typing import Optional

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.config import settings


class QueueService:
    """Service for enqueueing background jobs."""

    _pool: Optional[ArqRedis] = None

    @classmethod
    async def get_pool(cls) -> ArqRedis:
        """Get or create Redis connection pool."""
        if cls._pool is None:
            cls._pool = await create_pool(
                RedisSettings.from_dsn(settings.REDIS_URL)
            )
        return cls._pool

    @classmethod
    async def close_pool(cls) -> None:
        """Close Redis connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

    @classmethod
    async def enqueue_document_processing(
        cls,
        document_id: uuid.UUID,
        defer_seconds: int = 0,
    ) -> str:
        """
        Enqueue a document for processing.

        Args:
            document_id: UUID of the document to process
            defer_seconds: Delay before processing starts

        Returns:
            Job ID
        """
        pool = await cls.get_pool()
        job = await pool.enqueue_job(
            "process_document_job",
            str(document_id),
            _queue_name="document_queue",
            _defer_by=defer_seconds if defer_seconds > 0 else None,
        )
        return job.job_id

    @classmethod
    async def get_job_status(cls, job_id: str) -> Optional[dict]:
        """
        Get status of a job.

        Returns:
            Dict with job status or None if not found
        """
        pool = await cls.get_pool()
        job = await pool.job(job_id)
        if job:
            info = await job.info()
            return {
                "job_id": job_id,
                "status": job.status,
                "result": await job.result() if job.status == "complete" else None,
            }
        return None
