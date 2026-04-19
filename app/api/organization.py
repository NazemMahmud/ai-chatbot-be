"""
Organization API - Create, view, update organization and ownership transfer.

POST  /api/organization/transfer-ownership             → Request ownership transfer (owner only, checked in service)
GET   /api/organization/transfer-requests              → List transfer requests (org member)
POST  /api/organization/transfer-requests/{id}/{action} → Accept or decline transfer (target member, checked in service)
DELETE /api/organization/transfer-requests/{id}        → Cancel transfer (owner, checked in service)
"""
import uuid
import logging

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, OrgUser, DBSession
from app.enums.org import TransferAction
from app.schemas.common import ApiResponse
from app.schemas.organization import (
    CreateOrganizationRequest,
    UpdateOrganizationRequest,
    TransferOwnershipRequest,
    OrganizationData,
    OrganizationResponse,
    TransferRequestResponse,
    TransferRequestListData,
)
from app.services.organization import OrganizationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organization", tags=["organization"])


@router.post(
    "",
    response_model=ApiResponse[OrganizationData],
    status_code=status.HTTP_201_CREATED,
)
async def create_organization(
    data: CreateOrganizationRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Create an organization. Only for users without an existing organization.
    Create organization (after registration)
    """
    service = OrganizationService(db)
    org = await service.create_organization(
        name=data.name,
        owner_id=current_user.id,
    )

    return ApiResponse[OrganizationData](
        success=True,
        message="Organization created successfully",
        data=OrganizationData(
            data=OrganizationResponse.model_validate(org),
        ),
        statusCode=status.HTTP_201_CREATED,
    )


@router.get(
    "",
    response_model=ApiResponse[OrganizationData],
)
async def get_organization(
    db: DBSession,
    current_user: CurrentUser,
):
    """Get the current user's organization details. Returns empty data if no organization."""
    if not current_user.organization_id:
        return ApiResponse(success=True, data={})

    service = OrganizationService(db)
    org = await service.get_organization_for_member(current_user.organization_id)

    if not org:
        return ApiResponse(success=True, data={})

    return ApiResponse(
        success=True,
        data=OrganizationData(
            data=OrganizationResponse.model_validate(org),
        ),
    )


@router.patch(
    "",
    response_model=ApiResponse[OrganizationData],
)
async def update_organization(
    data: UpdateOrganizationRequest,
    db: DBSession,
    current_user: OrgUser,
):
    """Update organization settings. Owner check is enforced in service."""
    service = OrganizationService(db)
    org = await service.update_organization(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        name=data.name,
    )

    return ApiResponse(
        success=True,
        message="Organization updated successfully",
        data=OrganizationData(
            data=OrganizationResponse.model_validate(org),
        ),
    )


# todo: test LATER
@router.post(
    "/transfer-ownership",
    response_model=ApiResponse[TransferRequestResponse],
    status_code=status.HTTP_201_CREATED,
)
async def request_ownership_transfer(
    data: TransferOwnershipRequest,
    db: DBSession,
    current_user: OrgUser,
):
    """Request to transfer organization ownership to another member. Owner check in service."""
    service = OrganizationService(db)
    transfer = await service.request_ownership_transfer(
        organization_id=current_user.organization_id,
        from_user_id=current_user.id,
        to_user_id=data.target_user_id,
    )

    return ApiResponse(
        success=True,
        message="Ownership transfer request sent",
        data=TransferRequestResponse(
            id=transfer.id,
            organization_id=transfer.organization_id,
            organization_name=transfer.organization.name if transfer.organization else None,
            from_user_id=transfer.from_user_id,
            from_user_name=transfer.from_user.full_name if transfer.from_user else None,
            to_user_id=transfer.to_user_id,
            to_user_name=transfer.to_user.full_name if transfer.to_user else None,
            created_at=transfer.created_at,
        ),
        statusCode=status.HTTP_201_CREATED,
    )

# TODO: test LATER
@router.get(
    "/transfer-requests",
    response_model=ApiResponse[TransferRequestListData],
)
async def list_transfer_requests(
    db: DBSession,
    current_user: OrgUser,
):
    """List ownership transfer requests where the current user is sender or receiver."""
    service = OrganizationService(db)
    transfers = await service.list_transfer_requests_for_user(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
    )

    transfer_data = [
        TransferRequestResponse(
            id=t.id,
            organization_id=t.organization_id,
            organization_name=t.organization.name if t.organization else None,
            from_user_id=t.from_user_id,
            from_user_name=t.from_user.full_name if t.from_user else None,
            to_user_id=t.to_user_id,
            to_user_name=t.to_user.full_name if t.to_user else None,
            accepted_at=t.accepted_at,
            declined_at=t.declined_at,
            created_at=t.created_at,
        )
        for t in transfers
    ]

    return ApiResponse(
        success=True,
        data=TransferRequestListData(data=transfer_data),
    )

# TODO: test LATER
@router.post(
    "/transfer-requests/{transfer_id}/{action}",
    response_model=ApiResponse,
)
async def respond_to_transfer(
    transfer_id: uuid.UUID,
    action: TransferAction,
    db: DBSession,
    current_user: OrgUser,
):
    """Accept or decline an ownership transfer request. Target member check in service."""
    service = OrganizationService(db)
    await service.respond_to_transfer(
        transfer_id=transfer_id,
        user_id=current_user.id,
        action=action,
    )

    return ApiResponse(
        success=True,
        message=action.success_message,
    )


@router.delete(
    "/transfer-requests/{transfer_id}",
    response_model=ApiResponse,
)
async def cancel_ownership_transfer(
    transfer_id: uuid.UUID,
    db: DBSession,
    current_user: OrgUser,
):
    """Cancel a pending ownership transfer request. Owner check in service."""
    service = OrganizationService(db)
    await service.cancel_ownership_transfer(
        transfer_id=transfer_id,
        user_id=current_user.id,
    )

    return ApiResponse(
        success=True,
        message="Ownership transfer request cancelled.",
    )
