import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
        await self._check_email_available(data.email)

        user = await self._create_user(
            email=data.email,
            password=data.password,
            full_name=data.full_name,
        )

        org = await self._create_organization(
            name=data.organization_name,
            owner_id=user.id,
        )

        user.organization_id = org.id
        await self.db.flush()

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self._authenticate_user(email, password)

        org = await self._get_organization(user.organization_id)

        token = await self._issue_token(user.id)

        return TokenResponse(
            access_token=token,
            user=UserInfo(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                organization_name=org.name if org else None,
            ),
        )

    async def logout(self, jti: str) -> None:
        await self.db.execute(
            delete(UserToken).where(UserToken.jti == jti)
        )
        await self.db.flush()

    async def get_current_user_info(self, user: User) -> UserInfo:
        org = await self._get_organization(user.organization_id)

        return UserInfo(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            organization_id=user.organization_id,
            organization_name=org.name if org else None,
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
        result = await self.db.execute(select(User).where(User.email == email))
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

    async def _create_organization(self, name: str, owner_id) -> Organization:
        slug = await self._generate_unique_slug(name)

        org = Organization(
            name=name,
            slug=slug,
            owner_id=owner_id,
        )
        self.db.add(org)
        await self.db.flush()
        return org

    async def _generate_unique_slug(self, name: str) -> str:
        base_slug = self._slugify(name)
        slug = base_slug
        counter = 1
        while True:
            result = await self.db.execute(
                select(Organization).where(Organization.slug == slug)
            )
            if not result.scalar_one_or_none():
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

    async def _authenticate_user(self, email: str, password: str) -> User:
        result = await self.db.execute(
            select(User).where(User.email == email, User.is_active.is_(True))
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
            select(Organization).where(Organization.id == organization_id)
        )
        return result.scalar_one_or_none()
