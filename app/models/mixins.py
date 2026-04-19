"""
Reusable model mixins.

SoftDeleteMixin — adds `deleted_at` column for soft-delete support.
Records are never physically removed; they get a timestamp and are
filtered out of normal queries via `WHERE deleted_at IS NULL`.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """Mixin that adds soft-delete support via a deleted_at timestamp column."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    def soft_delete(self) -> None:
        """Mark this record as soft-deleted."""
        self.deleted_at = datetime.now(timezone.utc)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
