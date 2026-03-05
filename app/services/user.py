"""
User-related query service.

Provides reusable user lookups and membership checks
that can be consumed by MemberService, AuthService, etc.
"""
import uuid
import logging

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrgMember, User

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(
        self, email: str, *, raise_on_missing: bool = False
    ) -> User | None:
        """Find an active (non-deleted) user by email."""
        result = await self.db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if not user and raise_on_missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def check_user_is_org_member(
        self,
        email: str,
        organization_id: uuid.UUID,
    ) -> None:
        """
        non-deleted user AND is already a member
        single query with an EXISTS subquery (LEFT JOIN pattern)
        """
        # Single query: find user by email, and check membership in one go
        member_subq = (
            exists()
            .where(
                OrgMember.user_id == User.id,
                OrgMember.organization_id == organization_id,
                OrgMember.deleted_at.is_(None),
            )
            .correlate(User)
        )

        result = await self.db.execute(
            select(User.id, member_subq.label("is_member"))
            .where(User.email == email, User.deleted_at.is_(None))
        )
        row = result.one_or_none()

        if row is None:
            return

        if row.is_member:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this organization",
            )
