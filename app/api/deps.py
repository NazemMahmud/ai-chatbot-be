import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.user import User
from app.services.auth import AuthService

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer()

DBSession = Annotated[AsyncSession, Depends(get_session)]


async def get_auth_service(db: DBSession) -> AuthService:
    return AuthService(db)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    token = credentials.credentials
    payload = AuthService.decode_access_token(token)
    if not payload:
        logger.warning("Auth failed: token decode failed (expired or malformed)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    jti = payload.get("jti")
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

    result = await db.execute(
        select(User).where(User.id == user_uuid, User.is_active.is_(True))
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
