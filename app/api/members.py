"""
Members API - Organization member management and invitations (admin side).

Invitee-facing endpoints (accept/decline) are in app/api/invitations.py
"""
import uuid
import logging

from fastapi import APIRouter, Body, Depends, status

from app.api.deps import CurrentUser, DBSession, OrgUser
from app.services.permissions import PermissionService
from app.schemas.common import ApiResponse
from app.schemas.member import (
    ChangeRoleRequest,
    InviteMemberRequest,
    InvitationListData,
    InvitationResponse,
    LeaveContextData,
    LeaveOrganizationRequest,
    MakeInvitationResponse,
    OrgMemberListData,
    OrgMemberResponse,
)
from app.services.member import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["members"])


@router.get(
    "/leave-context",
    response_model=ApiResponse[LeaveContextData],
    status_code=status.HTTP_200_OK,
)
async def get_leave_context(
    db: DBSession,
    current_user: OrgUser,
):
    """Who is leaving (owner vs member), solo org, and transfer candidates (no members.read)."""
    service = MemberService(db)
    ctx = await service.get_leave_context(
        current_user.id, current_user.organization_id
    )
    return ApiResponse(
        success=True,
        data=LeaveContextData(**ctx),
    )


@router.post(
    "/leave",
    response_model=ApiResponse,
    status_code=status.HTTP_200_OK,
)
async def leave_organization(
    db: DBSession,
    current_user: OrgUser,
    payload: LeaveOrganizationRequest = Body(),
):
    """
    Self-service leave. Members leave immediately.
    Owners alone: organization is dissolved. Owners with teammates must either
    `transfer_to_user_id` (new owner) or `dissolve_organization` (free all members).
    """
    service = MemberService(db)
    await service.leave_organization(
        current_user.id,
        transfer_to_user_id=payload.transfer_to_user_id,
        dissolve_organization=payload.dissolve_organization,
    )

    return ApiResponse(
        success=True,
        message="You have left the organization",
    )


@router.get(
    "",
    response_model=ApiResponse[OrgMemberListData],
    dependencies=[Depends(PermissionService.Members.READ)],
)
async def list_members(
    db: DBSession,
    current_user: CurrentUser,
):
    """List all members of the current organization."""
    service = MemberService(db)
    members = await service.list_members(current_user.organization_id)

    member_data = [OrgMemberResponse(**m) for m in members]

    return ApiResponse(
        success=True,
        data=OrgMemberListData(data=member_data),
    )


@router.post(
    "/invite",
    response_model=ApiResponse[InvitationResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionService.Members.INVITE)],
)
async def invite_member(
    data: InviteMemberRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Invite a user to join the organization. Invitation appears on invitee's dashboard."""
    service = MemberService(db)
    invitation = await service.invite_member(
        organization_id=current_user.organization_id,
        email=data.email,
        role_id=data.role_id,
        invited_by=current_user.id,
    )

    return ApiResponse[InvitationResponse](
        success=True,
        message="Invitation sent successfully",
        data=InvitationResponse(
            id=invitation.id,
            email=invitation.email,
            role_id=invitation.role_id,
            role_name=invitation.role.name if invitation.role else None,
            accepted_at=invitation.accepted_at,
            declined_at=invitation.declined_at,
            created_at=invitation.created_at,
        ),
        statusCode=status.HTTP_201_CREATED,
    )


@router.patch(
    "/{user_id}/role",
    response_model=ApiResponse,
    dependencies=[Depends(PermissionService.Members.UPDATE)],
)
async def change_member_role(
    user_id: uuid.UUID,
    data: ChangeRoleRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Change a member's role. Requires members.update permission. Cannot change owner."""
    service = MemberService(db)
    await service.change_role(
        organization_id=current_user.organization_id,
        target_user_id=user_id,
        new_role_id=data.role_id,
        current_user_id=current_user.id,
    )

    return ApiResponse(
        success=True,
        message="Member role updated",
    )


@router.delete(
    "/{user_id}",
    response_model=ApiResponse,
    dependencies=[Depends(PermissionService.Members.REMOVE)],
)
async def remove_member(
    user_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Remove a member from the organization. Requires members.remove permission. Cannot remove owner."""
    service = MemberService(db)
    await service.remove_member(
        organization_id=current_user.organization_id,
        target_user_id=user_id,
        current_user_id=current_user.id,
    )

    return ApiResponse(
        success=True,
        message="Member removed from organization",
    )


@router.get(
    "/invitations",
    response_model=ApiResponse[InvitationListData],
    dependencies=[Depends(PermissionService.Members.INVITE)],
)
async def list_invitations(
    db: DBSession,
    current_user: CurrentUser,
):
    """List pending invitations sent by the organization. Requires members.invite permission."""
    service = MemberService(db)
    invitations = await service.list_invitations(current_user.organization_id)

    invitation_data = [
        InvitationResponse(
            id=inv.id,
            email=inv.email,
            role_id=inv.role_id,
            role_name=inv.role.name if inv.role else None,
            accepted_at=inv.accepted_at,
            declined_at=inv.declined_at,
            created_at=inv.created_at,
        )
        for inv in invitations
    ]

    return ApiResponse(
        success=True,
        data=InvitationListData(data=invitation_data),
    )


@router.delete(
    "/invitations/{invitation_id}",
    response_model=ApiResponse,
    dependencies=[Depends(PermissionService.Members.INVITE)],
)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Revoke a pending invitation. Requires members.invite permission."""
    service = MemberService(db)
    await service.revoke_invitation(
        organization_id=current_user.organization_id,
        invitation_id=invitation_id,
    )

    return ApiResponse(
        success=True,
        message="Invitation revoked",
    )
