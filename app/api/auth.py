"""
Auth API - Registration, login, logout, and current user info
"""
from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, CurrentUser
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserInfo
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=ApiResponse[None],
    status_code=status.HTTP_201_CREATED,
)
async def register(data: RegisterRequest, service: AuthServiceDep):
    """Register a new user and create an organization."""
    await service.register(data)
    return ApiResponse(success=True, message="Registration successful")


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(data: LoginRequest, service: AuthServiceDep):
    """Login with email and password."""
    result = await service.login(data.email, data.password)
    return ApiResponse(success=True, message="Login successful", data=result)


@router.post("/logout", response_model=ApiResponse[None])
async def logout(current_user: CurrentUser, service: AuthServiceDep):
    """Logout and invalidate the current token."""
    await service.logout(current_user.current_jti)
    return ApiResponse(success=True, message="Logged out successfully")


@router.get("/me", response_model=ApiResponse[UserInfo])
async def get_me(current_user: CurrentUser, service: AuthServiceDep):
    """Get current authenticated user info."""
    result = await service.get_current_user_info(current_user)
    return ApiResponse(success=True, data=result)
