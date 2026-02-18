"""
Storage Service - Handles file storage (local or MinIO/S3)
"""
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles

from app.config import settings


class StorageService(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    async def save(self, file_content: bytes, filename: str, content_type: str) -> str:
        """Save file and return the storage path/key."""
        pass

    @abstractmethod
    async def get(self, path: str) -> bytes:
        """Retrieve file content by path."""
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete file by path."""
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if file exists."""
        pass


class LocalStorageService(StorageService):
    """Local filesystem storage."""

    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or settings.STORAGE_LOCAL_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _generate_path(self, filename: str) -> Path:
        """Generate unique file path with uuid prefix."""
        ext = Path(filename).suffix
        unique_name = f"{uuid.uuid4()}{ext}"
        return self.base_path / unique_name

    async def save(self, file_content: bytes, filename: str, content_type: str) -> str:
        """Save file locally and return the path."""
        file_path = self._generate_path(filename)
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_content)
        return str(file_path)

    async def get(self, path: str) -> bytes:
        """Read file content."""
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> bool:
        """Delete file."""
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    async def exists(self, path: str) -> bool:
        """Check if file exists."""
        return os.path.exists(path)


class MinIOStorageService(StorageService):
    """MinIO/S3 storage."""

    def __init__(self):
        import boto3
        self.client = boto3.client(
            "s3",
            endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
        )
        self.bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Create bucket if it doesn't exist."""
        from botocore.exceptions import ClientError
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def _generate_key(self, filename: str) -> str:
        """Generate unique object key."""
        ext = Path(filename).suffix
        return f"documents/{uuid.uuid4()}{ext}"

    async def save(self, file_content: bytes, filename: str, content_type: str) -> str:
        """Upload to MinIO and return the object key."""
        key = self._generate_key(filename)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=file_content,
            ContentType=content_type,
        )
        return key

    async def get(self, path: str) -> bytes:
        """Download from MinIO."""
        response = self.client.get_object(Bucket=self.bucket, Key=path)
        return response["Body"].read()

    async def delete(self, path: str) -> bool:
        """Delete from MinIO."""
        from botocore.exceptions import ClientError
        try:
            self.client.delete_object(Bucket=self.bucket, Key=path)
            return True
        except ClientError:
            return False

    async def exists(self, path: str) -> bool:
        """Check if object exists."""
        from botocore.exceptions import ClientError
        try:
            self.client.head_object(Bucket=self.bucket, Key=path)
            return True
        except ClientError:
            return False


def get_storage_service() -> StorageService:
    """Factory function to get the configured storage service."""
    if settings.STORAGE_TYPE == "minio":
        return MinIOStorageService()
    return LocalStorageService()
