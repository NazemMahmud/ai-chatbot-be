import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Response, status
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.org_member import OrgMember
from app.models.organization import Organization
from app.models.user import User
from app.models.user_token import UserToken
from app.schemas.auth import RegisterRequest, TokenResponse, UserInfo

password_hash = PasswordHash.recommended()


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def register(self, data: RegisterRequest) -> None:
        """Register a new user. Organization is created separately after login."""
        await self._check_email_available(data.email)

        await self._create_user(
            email=data.email,
            password=data.password,
            full_name=data.full_name,
        )

    async def login(self, email: str, password: str) -> TokenResponse:
        user      = await self._authenticate_user(email, password)
        token     = await self._issue_token(user.id)
        user_info = await self._build_user_info(user)
        return TokenResponse(access_token=token, user=user_info)

    async def logout(self, jti: str) -> None:
        await self.db.execute(
            delete(UserToken).where(UserToken.jti == jti)
        )
        await self.db.flush()

    async def get_current_user_info(self, user: User) -> UserInfo:
        return await self._build_user_info(user)

    async def _build_user_info(self, user: User) -> UserInfo:
        """Build UserInfo including role and permissions from org membership."""
        org = await self._get_organization(user.organization_id)

        role_id: uuid.UUID | None = None
        role_name: str | None = None
        permissions: list[str] = []

        if user.organization_id:
            result = await self.db.execute(
                select(OrgMember).where(
                    OrgMember.user_id == user.id,
                    OrgMember.organization_id == user.organization_id,
                    OrgMember.deleted_at.is_(None),
                )
            )
            member = result.scalar_one_or_none()
            if member and member.role:
                role_id     = member.role_id
                role_name   = member.role.name
                permissions = [p.code for p in member.role.permissions]

        return UserInfo(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            organization_id=user.organization_id,
            organization_name=org.name if org else None,
            has_organization=org is not None,
            role_id=role_id,
            role_name=role_name,
            permissions=permissions,
        )

    # ------------------------------------------------------------------
    # Token whitelist check (static — called from deps.py)
    # ------------------------------------------------------------------

    @staticmethod
    async def is_token_whitelisted(db: AsyncSession, jti: str) -> bool:
        result = await db.execute(
            select(UserToken.id).where(UserToken.jti == jti)
        )
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Password hashing & JWT (static — no DB needed)
    # ------------------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        return password_hash.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return password_hash.verify(plain_password, hashed_password)

    @staticmethod
    def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(
            to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
        )

    @staticmethod
    def decode_access_token(token: str) -> dict | None:
        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
            )
            return payload
        except jwt.InvalidTokenError:
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _issue_token(self, user_id: uuid.UUID) -> str:
        """Generate a JWT with a unique jti and whitelist it in the DB."""
        jti = str(uuid.uuid4())
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        expires_at = datetime.now(timezone.utc) + expires_delta

        token = self.create_access_token(
            {"sub": str(user_id), "jti": jti},
            expires_delta=expires_delta,
        )

        await self._update_token(user_id, jti, expires_at)

        return token

    async def _update_token(self, user_id: uuid.UUID, jti: str, expires_at: datetime) -> None:
        """
            One user will have only one token at a time.
            So, delete any existing tokens for the user before issuing a new one.
            Then, insert the new token.
        """
        await self._revoke_existing_tokens(user_id)
        await self._create_token(user_id, jti, expires_at)

    async def _create_token(self, user_id: uuid.UUID, jti: str, expires_at: datetime) -> None:
        self.db.add(UserToken(
            user_id=user_id,
            jti=jti,
            expires_at=expires_at,
        ))

        await self.db.flush()


    async def _revoke_existing_tokens(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(UserToken).where(UserToken.user_id == user_id)
        )
        await self.db.flush()

    async def _check_email_available(self, email: str) -> None:
        result = await self.db.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )

    async def _create_user(
        self, email: str, password: str, full_name: str
    ) -> User:
        user = User(
            email=email,
            password=self.hash_password(password),
            full_name=full_name,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def _authenticate_user(self, email: str, password: str) -> User:
        result = await self.db.execute(
            select(User).where(
                User.email == email,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()

        if not user or not self.verify_password(password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        return user

    async def _get_organization(self, organization_id) -> Organization | None:
        if not organization_id:
            return None
        result = await self.db.execute(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def set_token_cookie(response: Response, token: str) -> None:
        is_prod = settings.APP_ENV != "development"
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=is_prod,
            samesite="lax",
            path="/",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    def clear_token_cookie(response: Response) -> None:
        is_prod = settings.APP_ENV != "development"
        response.delete_cookie(
            key="access_token",
            httponly=True,
            secure=is_prod,
            samesite="lax",
            path="/",
        )