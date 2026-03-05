"""
PermissionChecker — callable dependency for RBAC.
"""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.user import User

_security = HTTPBearer(auto_error=False)


async def _get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    db: AsyncSession = Depends(get_session),
) -> User:
    """
    Wrapper that delegates to deps.get_current_user at runtime.
    Defined here so PermissionChecker can reference it in its signature without importing deps.py at module level.
    """
    from app.api.deps import get_current_user
    return await get_current_user(request=request, credentials=credentials, db=db)


class PermissionChecker:
    """
        Checks if the current user has the specified permission (resource.action) in their organization.
        Usage: @router.post("", dependencies=[Depends(PermissionChecker("bots", "create"))])
    """

    def __init__(self, resource: str, action: str):
        self.resource = resource
        self.action = action

    async def __call__(
        self,
        current_user: User = Depends(_get_current_user),
        db: AsyncSession = Depends(get_session),
    ) -> None:
        from app.services.role import RoleService

        if not current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not part of any organization",
            )

        role_service = RoleService(db)
        has_permission = await role_service.user_has_permission(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            resource=self.resource,
            action=self.action,
        )

        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have permission: {self.resource}.{self.action}",
            )
