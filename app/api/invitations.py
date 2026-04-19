"""
Invitations API - Invitee-facing endpoints.

These routes are for the invited user (not the org admin).
They only require authentication — no org membership or permission checks,
since the invitee may not belong to any organization yet.

GET  /api/invitations/pending         → List my pending invitations
POST /api/invitations/{id}/accept     → Accept an invitation
POST /api/invitations/{id}/decline    → Decline an invitation
"""
import uuid
import logging

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.common import ApiResponse
from app.schemas.member import (
    PendingInvitationResponse,
    PendingInvitationListData,
)
from app.services.member import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.get(
    "/pending",
    response_model=ApiResponse[PendingInvitationListData],
)
async def list_pending_invitations(
    db: DBSession,
    current_user: CurrentUser,
):
    """List all pending invitations for the current user (matched by email)."""
    service = MemberService(db)
    invitations = await service.list_pending_invitations_for_user(
        email=current_user.email,
    )

    invitation_data = [
        PendingInvitationResponse(
            id=inv.id,
            organization_id=inv.organization_id,
            organization_name=inv.organization.name if inv.organization else None,
            role_id=inv.role_id,
            role_name=inv.role.name if inv.role else None,
            invited_by_name=inv.inviter.full_name if inv.inviter else None,
            created_at=inv.created_at,
        )
        for inv in invitations
    ]

    return ApiResponse(
        success=True,
        data=PendingInvitationListData(data=invitation_data),
    )


@router.post(
    "/{invitation_id}/accept",
    response_model=ApiResponse,
)
async def accept_invitation(
    invitation_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Accept a pending invitation and join the organization."""
    service = MemberService(db)
    await service.accept_invitation(
        invitation_id=invitation_id,
        user_id=current_user.id,
    )

    return ApiResponse(
        success=True,
        message="Invitation accepted. You are now a member of the organization.",
    )


@router.post(
    "/{invitation_id}/decline",
    response_model=ApiResponse,
)
async def decline_invitation(
    invitation_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Decline a pending invitation."""
    service = MemberService(db)
    await service.decline_invitation(
        invitation_id=invitation_id,
        user_id=current_user.id,
    )

    return ApiResponse(
        success=True,
        message="Invitation declined.",
    )
