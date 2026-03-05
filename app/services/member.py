"""
Organization member management service.

Handles invitations, role changes, and membership queries.
Uses dynamic role_id references instead of hardcoded role strings.

Invitation flow (in-app notification, no email/token):
1. Owner invites by email + role_id → OrgInvitation record created
2. Invitee sees pending invitations on their dashboard (matched by email)
3. Invitee accepts → OrgMember created, user.organization_id set
4. Invitee declines → invitation marked as declined
"""
import uuid
from datetime import datetime, timezone
import logging

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    OrgMember,
    OrgInvitation,
    OrgMembershipLeaveLog,
    Organization,
    OwnershipTransfer,
    User,
    Role,
)
from app.services.role import RoleService
from app.services.user import UserService

logger = logging.getLogger(__name__)


class MemberService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_members(self, organization_id: uuid.UUID) -> list[dict]:
        """List all members of an organization with user and role details."""
        result = await self.db.execute(
            select(OrgMember, User)
            .join(User, OrgMember.user_id == User.id)
            .where(
                OrgMember.organization_id == organization_id,
                OrgMember.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
            .order_by(OrgMember.created_at)
        )

        rows    = result.all()
        members = []
        for member, user in rows:
            members.append({
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role_id": member.role_id,
                "role_name": member.role.name if member.role else None,
                "created_at": member.created_at,
            })
        return members

    # ------------------------------------------------------------------
    # Invite member (owner/admin side)
    # ------------------------------------------------------------------

    async def invite_member(
        self,
        organization_id: uuid.UUID,
        email: str,
        role_id: uuid.UUID,
        invited_by: uuid.UUID,
    ) -> OrgInvitation:
        """
        Create an in-app invitation for a user to join the organization.
        No email or token is sent — the invitee sees it on their dashboard.
        """
        role = await self._get_role(role_id, organization_id)
        if role.is_system and role.name == "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot invite users with the owner role",
            )

        user_service = UserService(self.db)
        existing_user = await user_service.get_user_by_email(email)
        if existing_user and existing_user.organization_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This person is already registered and belongs to a different organization. "
                    "You cannot send an invitation until they leave that organization."
                ),
            )

        # Single query: check if user exists with this email AND is already a member
        await user_service.check_user_is_org_member(email, organization_id)

        # Check for existing pending invitation
        await self._invitation_exists_or_raise(
            organization_id=organization_id,
            email=email,
            pending_only=True,
        )

        invitation = OrgInvitation(
            organization_id=organization_id,
            email=email,
            role_id=role_id,
            invited_by=invited_by,
        )
        self.db.add(invitation)
        await self.db.flush()
        await self.db.refresh(invitation)
        return invitation

    # ------------------------------------------------------------------
    # Invitee-facing: list pending invitations for current user
    # ------------------------------------------------------------------

    async def list_pending_invitations_for_user(
        self, email: str
    ) -> list[OrgInvitation]:
        """List all pending invitations for a user by email (invitee dashboard)."""
        result = await self.db.execute(
            select(OrgInvitation)
            .where(
                OrgInvitation.email == email,
                OrgInvitation.accepted_at.is_(None),
                OrgInvitation.declined_at.is_(None),
                OrgInvitation.deleted_at.is_(None),
            )
            .order_by(OrgInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Accept invitation (invitee side)
    # ------------------------------------------------------------------

    async def accept_invitation(
        self, invitation_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrgMember:
        """Accept an invitation by ID and add user to the organization."""
        invitation = await self._get_pending_invitation(invitation_id)

        # Verify the invitation is for this user's email
        user = await self._get_active_user(user_id)
        if user.email != invitation.email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This invitation is for a different email address",
            )

        # User must not already belong to an organization
        if user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already belong to an organization. Leave your current organization first.",
            )

        existing_rs = await self.db.execute(
            select(OrgMember).where(
                OrgMember.organization_id == invitation.organization_id,
                OrgMember.user_id == user_id,
            )
        )
        existing_member = existing_rs.scalar_one_or_none()
        if existing_member and existing_member.deleted_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You are already a member of this organization",
            )

        if existing_member:
            existing_member.deleted_at = None
            existing_member.role_id = invitation.role_id
            existing_member.invited_by = invitation.invited_by
            member = existing_member
        else:
            member = OrgMember(
                organization_id=invitation.organization_id,
                user_id=user_id,
                role_id=invitation.role_id,
                invited_by=invitation.invited_by,
            )
            self.db.add(member)

        user.organization_id = invitation.organization_id

        # Mark invitation as accepted
        invitation.accepted_at = datetime.now(timezone.utc)

        await self.db.flush()
        return member

    # ------------------------------------------------------------------
    # Decline invitation (invitee side)
    # ------------------------------------------------------------------

    async def decline_invitation(
        self, invitation_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrgInvitation:
        """Decline an invitation."""
        invitation = await self._get_pending_invitation(invitation_id)

        # Verify the invitation is for this user's email
        user = await self._get_active_user(user_id)
        if user.email != invitation.email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This invitation is for a different email address",
            )

        invitation.declined_at = datetime.now(timezone.utc)
        await self.db.flush()
        return invitation

    # ------------------------------------------------------------------
    # Change role
    # ------------------------------------------------------------------

    async def change_role(
        self,
        organization_id: uuid.UUID,
        target_user_id: uuid.UUID,
        new_role_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> OrgMember:
        """Change a member's role. Cannot change owner's role."""
        # Validate new role belongs to this org (need object to check is_system)
        new_role = await self._get_role(new_role_id, organization_id)

        result = await self.db.execute(
            select(OrgMember).where(
                OrgMember.organization_id == organization_id,
                OrgMember.user_id == target_user_id,
                OrgMember.deleted_at.is_(None),
            )
        )
        member = result.scalar_one_or_none()

        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found",
            )

        # Cannot change owner's role
        if member.role and member.role.is_system and member.role.name == "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot change the owner's role",
            )

        # Cannot assign owner role to someone
        if new_role.is_system and new_role.name == "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot assign the owner role",
            )

        if target_user_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot change your own role",
            )

        member.role_id = new_role_id
        await self.db.flush()
        return member

    # ------------------------------------------------------------------
    # Remove member
    # ------------------------------------------------------------------

    async def remove_member(
        self,
        organization_id: uuid.UUID,
        target_user_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> None:
        """Remove a member from the organization. Cannot remove owner."""
        result = await self.db.execute(
            select(OrgMember).where(
                OrgMember.organization_id == organization_id,
                OrgMember.user_id == target_user_id,
                OrgMember.deleted_at.is_(None),
            )
        )
        member = result.scalar_one_or_none()

        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found",
            )

        if member.role and member.role.is_system and member.role.name == "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove the organization owner",
            )

        if target_user_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove yourself",
            )

        # Clear user's organization_id
        user_result = await self.db.execute(
            select(User).where(User.id == target_user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            user.organization_id = None

        member.soft_delete()
        await self.db.flush()

    async def get_leave_context(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> dict:
        """Return owner/solo state and other members for leave-org UI (no members.read required)."""
        members = await self.list_members(organization_id)
        me = next((m for m in members if m["user_id"] == user_id), None)
        if not me:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You are not a member of this organization",
            )
        others = [m for m in members if m["user_id"] != user_id]
        role_name = (me.get("role_name") or "").lower()
        is_owner = role_name == "owner"
        org_row = await self.db.execute(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.deleted_at.is_(None),
            )
        )
        org = org_row.scalar_one_or_none()
        return {
            "is_owner": is_owner,
            "organization_name": org.name if org else None,
            "solo_owner": is_owner and len(others) == 0,
            "other_members": [
                {
                    "user_id": m["user_id"],
                    "email": m["email"],
                    "full_name": m["full_name"],
                }
                for m in others
            ],
        }

    async def leave_organization(
        self,
        user_id: uuid.UUID,
        *,
        transfer_to_user_id: uuid.UUID | None = None,
        dissolve_organization: bool = False,
    ) -> None:
        """
        Self-service leave. Non-owners simply leave.
        Owners: if alone, organization is dissolved. If others exist, must either
        transfer ownership to another member or dissolve the organization (all members freed).
        """
        result = await self.db.execute(
            select(OrgMember)
            .options(selectinload(OrgMember.role))
            .where(
                OrgMember.user_id == user_id,
                OrgMember.deleted_at.is_(None),
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You are not a member of any organization",
            )

        org_id = member.organization_id
        is_owner = bool(
            member.role
            and member.role.is_system
            and member.role.name == "owner"
        )

        total = await self.db.scalar(
            select(func.count()).select_from(OrgMember).where(
                OrgMember.organization_id == org_id,
                OrgMember.deleted_at.is_(None),
            )
        )
        total_members = int(total or 0)
        other_count = total_members - 1

        if not is_owner:
            if transfer_to_user_id is not None or dissolve_organization:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only the organization owner can transfer ownership or dissolve the organization.",
                )
            await self._leave_non_owner(user_id, member, org_id)
            return

        if other_count <= 0:
            await self._dissolve_organization(org_id)
            return

        if transfer_to_user_id is not None and dissolve_organization:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Choose either a new owner or dissolution, not both.",
            )

        if transfer_to_user_id is not None:
            await self._owner_transfer_and_leave(
                leaver_id=user_id,
                org_id=org_id,
                transfer_to_user_id=transfer_to_user_id,
            )
            return

        if dissolve_organization:
            await self._dissolve_organization(org_id)
            return

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Choose another member to receive ownership, or dissolve the organization. "
                "Dissolving removes all members from the organization."
            ),
        )

    async def _leave_non_owner(
        self, user_id: uuid.UUID, member: OrgMember, org_id: uuid.UUID
    ) -> None:
        role_id = member.role_id
        self.db.add(
            OrgMembershipLeaveLog(
                user_id=user_id,
                organization_id=org_id,
                role_id=role_id,
                voluntary=True,
            )
        )
        user = await self._get_active_user(user_id)
        user.organization_id = None
        member.soft_delete()
        await self.db.flush()

    async def _owner_transfer_and_leave(
        self,
        *,
        leaver_id: uuid.UUID,
        org_id: uuid.UUID,
        transfer_to_user_id: uuid.UUID,
    ) -> None:
        if transfer_to_user_id == leaver_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Choose another member as the new owner.",
            )

        leaver_rs = await self.db.execute(
            select(OrgMember)
            .options(selectinload(OrgMember.role))
            .where(
                OrgMember.user_id == leaver_id,
                OrgMember.organization_id == org_id,
                OrgMember.deleted_at.is_(None),
            )
        )
        leaver_member = leaver_rs.scalar_one_or_none()
        if not leaver_member or not leaver_member.role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership not found",
            )
        if not (leaver_member.role.is_system and leaver_member.role.name == "owner"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the organization owner can transfer ownership.",
            )

        org_rs = await self.db.execute(
            select(Organization).where(
                Organization.id == org_id,
                Organization.deleted_at.is_(None),
            )
        )
        org = org_rs.scalar_one_or_none()
        if not org or org.owner_id != leaver_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization owner mismatch.",
            )

        tgt_rs = await self.db.execute(
            select(OrgMember).where(
                OrgMember.user_id == transfer_to_user_id,
                OrgMember.organization_id == org_id,
                OrgMember.deleted_at.is_(None),
            )
        )
        tgt_member = tgt_rs.scalar_one_or_none()
        if not tgt_member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Selected user is not a member of this organization.",
            )

        role_service = RoleService(self.db)
        owner_role = await role_service.get_owner_role(org_id)

        org.owner_id = transfer_to_user_id
        tgt_member.role_id = owner_role.id

        self.db.add(
            OrgMembershipLeaveLog(
                user_id=leaver_id,
                organization_id=org_id,
                role_id=leaver_member.role_id,
                voluntary=True,
            )
        )
        leaver_member.soft_delete()
        leaver_user = await self._get_active_user(leaver_id)
        leaver_user.organization_id = None
        await self.db.flush()

    async def _dissolve_organization(self, org_id: uuid.UUID) -> None:
        """
        Remove every active member from the organization (soft-delete memberships),
        clear their organization_id, soft-delete invitations and transfer requests,
        soft-delete the organization and its roles. Rows are retained for analytics.
        """
        now = datetime.now(timezone.utc)
        mem_rs = await self.db.execute(
            select(OrgMember).where(
                OrgMember.organization_id == org_id,
                OrgMember.deleted_at.is_(None),
            )
        )
        members = list(mem_rs.scalars().all())
        for m in members:
            u_rs = await self.db.execute(select(User).where(User.id == m.user_id))
            user = u_rs.scalar_one_or_none()
            if user and user.organization_id == org_id:
                user.organization_id = None
            self.db.add(
                OrgMembershipLeaveLog(
                    user_id=m.user_id,
                    organization_id=org_id,
                    role_id=m.role_id,
                    voluntary=False,
                )
            )
            m.soft_delete()

        await self.db.execute(
            update(OrgInvitation)
            .where(
                OrgInvitation.organization_id == org_id,
                OrgInvitation.deleted_at.is_(None),
            )
            .values(deleted_at=now)
        )
        await self.db.execute(
            update(OwnershipTransfer)
            .where(
                OwnershipTransfer.organization_id == org_id,
                OwnershipTransfer.deleted_at.is_(None),
            )
            .values(deleted_at=now)
        )

        r_rs = await self.db.execute(
            select(Role).where(
                Role.organization_id == org_id,
                Role.deleted_at.is_(None),
            )
        )
        for role in r_rs.scalars():
            role.deleted_at = now

        o_rs = await self.db.execute(
            select(Organization).where(
                Organization.id == org_id,
                Organization.deleted_at.is_(None),
            )
        )
        org = o_rs.scalar_one_or_none()
        if org:
            org.soft_delete()
        await self.db.flush()

    # ------------------------------------------------------------------
    # Invitations management (org admin side)
    # ------------------------------------------------------------------

    async def list_invitations(
        self, organization_id: uuid.UUID
    ) -> list[OrgInvitation]:
        """List pending (non-accepted, non-declined) invitations for the org."""
        result = await self.db.execute(
            select(OrgInvitation)
            .where(
                OrgInvitation.organization_id == organization_id,
                OrgInvitation.accepted_at.is_(None),
                OrgInvitation.declined_at.is_(None),
                OrgInvitation.deleted_at.is_(None),
            )
            .order_by(OrgInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_invitation(
        self, organization_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> None:
        """Delete/revoke a pending invitation."""
        result = await self.db.execute(
            select(OrgInvitation).where(
                OrgInvitation.id == invitation_id,
                OrgInvitation.organization_id == organization_id,
                OrgInvitation.accepted_at.is_(None),
                OrgInvitation.declined_at.is_(None),
                OrgInvitation.deleted_at.is_(None),
            )
        )
        invitation = result.scalar_one_or_none()

        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )

        invitation.soft_delete()
        await self.db.flush()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_pending_invitation(
        self, invitation_id: uuid.UUID
    ) -> OrgInvitation:
        """Get a pending invitation by ID."""
        result = await self.db.execute(
            select(OrgInvitation).where(
                OrgInvitation.id == invitation_id,
                OrgInvitation.accepted_at.is_(None),
                OrgInvitation.declined_at.is_(None),
                OrgInvitation.deleted_at.is_(None),
            )
        )
        invitation = result.scalar_one_or_none()
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pending invitation not found",
            )
        return invitation

    async def _get_active_user(self, user_id: uuid.UUID) -> User:
        """Get an active, non-deleted user."""
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

    async def _invitation_exists_or_raise(
        self,
        *,
        organization_id: uuid.UUID | None = None,
        email: str | None = None,
        pending_only: bool = False,
    ) -> None:
        """
        invitation existence check
        Only non-None keyword arguments are added as filters, so callers can check by any combination of columns.
        """
        filters = []
        if organization_id is not None:
            filters.append(OrgInvitation.organization_id == organization_id)
        if email is not None:
            filters.append(OrgInvitation.email == email)
        if pending_only:
            filters.append(OrgInvitation.accepted_at.is_(None))
            filters.append(OrgInvitation.declined_at.is_(None))
            filters.append(OrgInvitation.deleted_at.is_(None))

        if not filters:
            return

        result = await self.db.execute(
            select(exists().where(*filters))
        )
        if result.scalar():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A pending invitation already exists for this email",
            )

    async def _role_exists_or_raise(
        self, role_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        """ verify the role exists in the org. """
        result = await self.db.execute(
            select(
                exists().where(
                    Role.id == role_id,
                    Role.organization_id == organization_id,
                    Role.deleted_at.is_(None),
                )
            )
        )
        if not result.scalar():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found in this organization",
            )

    async def _get_role(
        self,
        role_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> Role:
        """Load a role. Optionally filter by organization_id."""
        filters = [Role.id == role_id, Role.deleted_at.is_(None)]
        if organization_id is not None:
            filters.append(Role.organization_id == organization_id)

        result = await self.db.execute(select(Role).where(*filters))
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found",
            )
        return role
