"""
Bots API - CRUD operations for chatbots
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DBSession
from app.schemas import ApiResponse, BotCreate, BotUpdate, BotResponse, BotListData
from app.schemas.bot import BotPickerListData
from app.services.bot import BotService
from app.services.permissions import PermissionService

router = APIRouter(prefix="/bots", tags=["bots"])


@router.post(
    "",
    response_model=ApiResponse[BotResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(PermissionService.Bots.CREATE)],
)
async def create_bot(
    data: BotCreate,
    db: DBSession,
    current_user: CurrentUser,
):
    """Create a new bot."""
    service = BotService(db)
    bot = await service.create_bot(data, current_user.organization_id)
    return ApiResponse(success=True, message="Bot created successfully", data=bot, statusCode=status.HTTP_201_CREATED)


@router.get(
    "",
    response_model=ApiResponse[BotListData],
    dependencies=[Depends(PermissionService.Bots.READ)],
)
async def list_bots(
    db: DBSession,
    current_user: CurrentUser,
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List all bots with pagination, sorted by created_at descending."""
    service = BotService(db)
    result = await service.list_bots(
        current_user.organization_id, is_active, limit, offset
    )
    return ApiResponse(success=True, data=result, statusCode=status.HTTP_200_OK)


@router.get(
    "/picker",
    response_model=ApiResponse[BotPickerListData],
    dependencies=[Depends(PermissionService.Bots.READ)],
)
async def bot_picker(
    db: DBSession,
    current_user: CurrentUser,
    search: Optional[str] = Query(None, description="Search by bot name (case-insensitive)"),
):
    """
    Lightweight bot list for picker/select components (e.g. documents page).

    Returns only id + name of active bots. Supports search by name.
    Default limit is 20, configurable based on subscription package later.
    """
    service = BotService(db)
    result = await service.search_bots_for_picker(
        current_user.organization_id, search
    )
    return ApiResponse(success=True, data=result, statusCode=status.HTTP_200_OK)


@router.get(
    "/{bot_id}",
    response_model=ApiResponse[BotResponse],
    dependencies=[Depends(PermissionService.Bots.READ)],
)
async def get_bot(
    bot_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Get a specific bot by ID."""
    service = BotService(db)
    bot = await service.get_bot(bot_id, current_user.organization_id)
    return ApiResponse(success=True, data=bot, statusCode=status.HTTP_200_OK)


@router.patch(
    "/{bot_id}",
    response_model=ApiResponse[BotResponse],
    dependencies=[Depends(PermissionService.Bots.UPDATE)],
)
async def update_bot(
    bot_id: uuid.UUID,
    data: BotUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    """Update a bot."""
    service = BotService(db)
    bot = await service.update_bot(bot_id, data, current_user.organization_id)
    return ApiResponse(
        success=True,
        message="Bot updated successfully",
        data=bot,
        statusCode=status.HTTP_200_OK,
    )


@router.delete(
    "/{bot_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(PermissionService.Bots.DELETE)],
)
async def delete_bot(
    bot_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Delete a bot and all its documents."""
    service = BotService(db)
    await service.delete_bot(bot_id, current_user.organization_id)
    return ApiResponse(
        success=True,
        message="Bot deleted successfully",
        statusCode=status.HTTP_200_OK,
    )
