"""
Organization management service.

Handles organization creation, updates, and ownership transfer.
"""
import re
import uuid
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, OrgMember, User
from app.models.ownership_transfer import OwnershipTransfer
from app.models.role import Role
from app.enums.org import TransferAction
from app.services.role import RoleService

logger = logging.getLogger(__name__)


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # todo: tightly coupled
    async def create_organization(
        self, name: str, owner_id: uuid.UUID
    ) -> Organization:
        """
        Create an organization for a user who registered without one. (post-registration)
        Sets user.organization_id, seeds default roles, creates OrgMember.
        """
        user = await self._get_user(owner_id)
        if user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already belong to an organization",
            )

        slug = await self._generate_unique_slug(name)

        org = Organization(
            name=name,
            slug=slug,
            owner_id=owner_id,
        )
        self.db.add(org)
        await self.db.flush()

        user.organization_id = org.id
        await self.db.flush()

        # Create default roles (owner, admin, member) with permissions
        role_service = RoleService(self.db)
        roles = await role_service.create_default_roles(org.id)

        # Add user as org member with owner role
        self.db.add(OrgMember(
            organization_id=org.id,
            user_id=owner_id,
            role_id=roles["owner"].id,
        ))
        await self.db.flush()

        return org

    async def get_organization(self, organization_id: uuid.UUID) -> Organization | None:
        result = await self.db.execute(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_organization_for_member(
        self, organization_id: uuid.UUID
    ) -> Organization | None:
        """Return org if it exists. The caller (authenticated user) already has organization_id set."""
        return await self.get_organization(organization_id)

    async def update_organization(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
    ) -> Organization:
        org = await self._get_organization_or_raise(organization_id)

        if org.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the organization owner can update organization settings",
            )

        org.name = name

        await self.db.flush()
        await self.db.refresh(org)
        return org

    # ------------------------------------------------------------------
    # Request ownership transfer (owner only)
    # ------------------------------------------------------------------

    async def request_ownership_transfer(
        self,
        organization_id: uuid.UUID,
        from_user_id: uuid.UUID,
        to_user_id: uuid.UUID,
    ) -> OwnershipTransfer:
        org = await self._get_organization_or_raise(organization_id)

        # Only the current owner can initiate transfer
        if org.owner_id != from_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the organization owner can transfer ownership",
            )

        # Cannot transfer to yourself
        if from_user_id == to_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot transfer ownership to yourself",
            )

        # Target must be a member of the organization
        member_exists = await self.db.execute(
            select(
                exists().where(
                    OrgMember.organization_id == organization_id,
                    OrgMember.user_id == to_user_id,
                    OrgMember.deleted_at.is_(None),
                )
            )
        )
        if not member_exists.scalar():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target user is not a member of this organization",
            )

        # Check for existing pending transfer request
        pending_exists = await self.db.execute(
            select(
                exists().where(
                    OwnershipTransfer.organization_id == organization_id,
                    OwnershipTransfer.accepted_at.is_(None),
                    OwnershipTransfer.declined_at.is_(None),
                    OwnershipTransfer.deleted_at.is_(None),
                )
            )
        )
        if pending_exists.scalar():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A pending ownership transfer request already exists",
            )

        transfer = OwnershipTransfer(
            organization_id=organization_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
        )
        self.db.add(transfer)
        await self.db.flush()
        await self.db.refresh(transfer)
        return transfer

    # ------------------------------------------------------------------
    # Respond to ownership transfer (accept / decline)
    # ------------------------------------------------------------------

    async def respond_to_transfer(
        self,
        transfer_id: uuid.UUID,
        user_id: uuid.UUID,
        action: TransferAction,
    ) -> OwnershipTransfer:
        """Accept or decline an ownership transfer request."""
        transfer = await self._get_pending_transfer(transfer_id)

        if transfer.to_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This transfer request is not for you",
            )

        if action == TransferAction.ACCEPT:
            # Get role service for role swaps
            role_service = RoleService(self.db)
            owner_role = await role_service.get_owner_role(transfer.organization_id)
            member_role = await self._get_default_member_role(transfer.organization_id)

            # Swap roles: previous owner → member
            prev_owner_member = await self._get_org_member(
                transfer.organization_id, transfer.from_user_id
            )
            prev_owner_member.role_id = member_role.id

            # Swap roles: target → owner
            new_owner_member = await self._get_org_member(
                transfer.organization_id, transfer.to_user_id
            )
            new_owner_member.role_id = owner_role.id

            # Update organization.owner_id
            org = await self._get_organization_or_raise(transfer.organization_id)
            org.owner_id = transfer.to_user_id

            transfer.accepted_at = datetime.now(timezone.utc)

        elif action == TransferAction.DECLINE:
            transfer.declined_at = datetime.now(timezone.utc)

        await self.db.flush()
        return transfer

    # ------------------------------------------------------------------
    # Cancel ownership transfer (owner cancels their own request)
    # ------------------------------------------------------------------

    async def cancel_ownership_transfer(
        self,
        transfer_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        transfer = await self._get_pending_transfer(transfer_id)

        if transfer.from_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the requester can cancel a transfer request",
            )

        transfer.soft_delete()
        await self.db.flush()

    # ------------------------------------------------------------------
    # List transfer requests for an organization
    # ------------------------------------------------------------------

    async def list_transfer_requests_for_user(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[OwnershipTransfer]:
        """List transfers where the user is sender or receiver."""
        result = await self.db.execute(
            select(OwnershipTransfer)
            .where(
                OwnershipTransfer.organization_id == organization_id,
                OwnershipTransfer.deleted_at.is_(None),
                or_(
                    OwnershipTransfer.from_user_id == user_id,
                    OwnershipTransfer.to_user_id == user_id,
                ),
            )
            .order_by(OwnershipTransfer.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_organization_or_raise(self, organization_id: uuid.UUID) -> Organization:
        org = await self.get_organization(organization_id)
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
        return org

    async def _get_user(self, user_id: uuid.UUID) -> User:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def _get_pending_transfer(
        self, transfer_id: uuid.UUID
    ) -> OwnershipTransfer:
        result = await self.db.execute(
            select(OwnershipTransfer).where(
                OwnershipTransfer.id == transfer_id,
                OwnershipTransfer.accepted_at.is_(None),
                OwnershipTransfer.declined_at.is_(None),
                OwnershipTransfer.deleted_at.is_(None),
            )
        )
        transfer = result.scalar_one_or_none()
        if not transfer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pending transfer request not found",
            )
        return transfer

    async def _get_org_member(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrgMember:
        result = await self.db.execute(
            select(OrgMember).where(
                OrgMember.organization_id == organization_id,
                OrgMember.user_id == user_id,
                OrgMember.deleted_at.is_(None),
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in organization",
            )
        return member

    async def _get_default_member_role(
        self, organization_id: uuid.UUID
    ) -> Role:
        """Get the default 'member' role for role demotion on ownership transfer."""
        result = await self.db.execute(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.name == "member",
                Role.is_system.is_(False),
            )
        )
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default member role not found for organization",
            )
        return role

    async def _generate_unique_slug(self, name: str) -> str:
        base_slug = self._slugify(name)
        slug = base_slug
        counter = 1
        while True:
            result = await self.db.execute(
                select(
                    exists().where(
                        Organization.slug == slug,
                        Organization.deleted_at.is_(None),
                    )
                )
            )
            if not result.scalar():
                return slug
            slug = f"{base_slug}-{counter}"
            counter += 1

    @staticmethod
    def _slugify(name: str) -> str:
        slug = name.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s-]+", "-", slug)
        slug = slug.strip("-")
        return slug or "org"
