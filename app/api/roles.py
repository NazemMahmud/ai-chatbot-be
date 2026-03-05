"""
Roles API - Manage custom roles and view permissions.
"""
import uuid
import logging

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DBSession
from app.services.permissions import PermissionService
from app.schemas.common import ApiResponse
from app.schemas.role import (
    PermissionGroupResponse,
    PermissionListData,
    PermissionPickerItem,
    PermissionPickerListData,
    PermissionResponse,
    RoleCreateRequest,
    RoleListData,
    RolePickerItem,
    RolePickerListData,
    RoleResponse,
    RoleUpdateRequest,
)
from app.services.role import RoleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get(
    "/permissions",
    response_model=ApiResponse[PermissionListData],
    dependencies=[Depends(PermissionService.Roles.READ)],
)
async def list_permissions(db: DBSession, current_user: CurrentUser):
    """List all available system permissions."""
    service = RoleService(db)
    permissions = await service.list_permissions()

    return ApiResponse(
        success=True,
        data=PermissionListData(
            data=[PermissionResponse.model_validate(p) for p in permissions]
        ),
    )


@router.get(
    "/permissions/picker",
    response_model=ApiResponse[PermissionPickerListData],
    dependencies=[Depends(PermissionService.Roles.READ)],
)
async def permission_picker(db: DBSession, current_user: CurrentUser):
    """
    Permissions grouped by resource for picker/checkbox UI.
    Used in create-role and edit-role forms.
    Returns: [{resource: "bots", permissions: [{id, action, description}, ...]}, ...]
    """
    service = RoleService(db)
    grouped = await service.list_permissions_grouped()

    return ApiResponse(
        success=True,
        data=PermissionPickerListData(
            data=[
                PermissionGroupResponse(
                    resource=resource,
                    permissions=[
                        PermissionPickerItem.model_validate(p)
                        for p in perms
                    ],
                )
                for resource, perms in grouped.items()
            ]
        ),
    )


@router.get(
    "",
    response_model=ApiResponse[RoleListData],
    dependencies=[Depends(PermissionService.Roles.READ)],
)
async def list_roles(db: DBSession, current_user: CurrentUser):
    """List all roles for the current organization."""
    service = RoleService(db)
    roles = await service.list_roles(current_user.organization_id)

    return ApiResponse(
        success=True,
        data=RoleListData(
            data=[RoleResponse.model_validate(r) for r in roles]
        ),
    )


@router.get(
    "/picker",
    response_model=ApiResponse[RolePickerListData],
    dependencies=[Depends(PermissionService.Roles.READ)],
)
async def role_picker(db: DBSession, current_user: CurrentUser):
    """
    Lightweight role list for picker/select dropdowns (e.g. invite member form).

    Returns only id, name, and is_system. Excludes the "owner" system role
    since it cannot be assigned to invited members.
    """
    service = RoleService(db)
    roles = await service.list_roles(current_user.organization_id)

    picker_data = [
        RolePickerItem.model_validate(r)
        for r in roles
        if not (r.is_system and r.name == "owner")
    ]

    return ApiResponse(
        success=True,
        data=RolePickerListData(data=picker_data),
    )


@router.get(
    "/{role_id}",
    response_model=ApiResponse[RoleResponse],
    dependencies=[Depends(PermissionService.Roles.READ)],
)
async def get_role(
    role_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Get a specific role with its permissions."""
    service = RoleService(db)
    role = await service.get_role(role_id, current_user.organization_id)

    return ApiResponse(
        success=True,
        data=RoleResponse.model_validate(role),
    )


@router.post(
    "",
    response_model=ApiResponse[RoleResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionService.Roles.CREATE)],
)
async def create_role(
    data: RoleCreateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Create a new custom role for the organization."""
    service = RoleService(db)
    role = await service.create_role(
        organization_id=current_user.organization_id,
        name=data.name,
        description=data.description,
        permission_ids=data.permission_ids,
    )

    return ApiResponse(
        success=True,
        message="Role created successfully",
        data=RoleResponse.model_validate(role),
        statusCode=status.HTTP_201_CREATED,
    )


@router.patch(
    "/{role_id}",
    response_model=ApiResponse[RoleResponse],
    dependencies=[Depends(PermissionService.Roles.UPDATE)],
)
async def update_role(
    role_id: uuid.UUID,
    data: RoleUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Update a custom role. System roles cannot be modified."""
    service = RoleService(db)
    role = await service.update_role(
        role_id=role_id,
        organization_id=current_user.organization_id,
        name=data.name,
        description=data.description,
        permission_ids=data.permission_ids,
    )

    return ApiResponse(
        success=True,
        message="Role updated successfully",
        data=RoleResponse.model_validate(role),
    )


@router.delete(
    "/{role_id}",
    response_model=ApiResponse,
    dependencies=[Depends(PermissionService.Roles.DELETE)],
)
async def delete_role(
    role_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Delete a custom role. System roles cannot be deleted."""
    service = RoleService(db)
    await service.delete_role(role_id, current_user.organization_id)

    return ApiResponse(
        success=True,
        message="Role deleted successfully",
    )
