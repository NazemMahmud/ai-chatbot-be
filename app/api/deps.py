import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.user import User
from app.services.auth import AuthService

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)

DBSession = Annotated[AsyncSession, Depends(get_session)]


async def get_auth_service(db: DBSession) -> AuthService:
    return AuthService(db)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

def get_payload(token: str) -> dict:
    payload = AuthService.decode_access_token(token)
    if not payload:
        logger.warning("Auth failed: token decode failed (expired or malformed)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    token = request.cookies.get("access_token")
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = get_payload(token)
    user_id = payload.get("sub") # type: ignore
    jti     = payload.get("jti") # type: ignore

    if not user_id or not jti:
        logger.warning("Auth failed: token missing 'sub' or 'jti' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        logger.warning(f"Auth failed: 'sub' is not a valid UUID — sub={user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    if not await AuthService.is_token_whitelisted(db, jti):
        logger.warning(f"Auth failed: jti not whitelisted (revoked/logged out) — jti={jti}, user_id={user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # todo: later shift this to auth service or user service including the not user error handling
    result = await db.execute(
        select(User).where(
            User.id == user_uuid,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"Auth failed: user not found or inactive — user_id={user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    user.current_jti = jti

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_organization(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensures the authenticated user belongs to an organization."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not belong to any organization",
        )
    return current_user


OrgUser = Annotated[User, Depends(require_organization)]
