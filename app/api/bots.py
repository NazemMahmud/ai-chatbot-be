"""
Bots API - CRUD operations for chatbots
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Query, status

from app.api.deps import DBSession
from app.schemas import ApiResponse, BotCreate, BotUpdate, BotResponse, BotListData
from app.services.bot import BotService

router = APIRouter(prefix="/bots", tags=["bots"])

# TODO: add organization later, update route with organization id and user id


# org_id: uuid.UUID, current_user: CurrentUser
@router.post(
    "",
    response_model=ApiResponse[BotResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_bot(
    data: BotCreate,
    db: DBSession,
):
    """Create a new bot."""
    service = BotService(db)
    bot = await service.create_bot(data)
    return ApiResponse(success=True, message="Bot created successfully", data=bot)


@router.get("", response_model=ApiResponse[BotListData])
async def list_bots(
    db: DBSession,
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
   
):
    """List all bots with pagination, sorted by created_at descending."""
    service = BotService(db)
    result = await service.list_bots(is_active, limit, offset)
    return ApiResponse(success=True, data=result, statusCode=status.HTTP_200_OK)


@router.get("/{bot_id}", response_model=ApiResponse[BotResponse])
async def get_bot(
    bot_id: uuid.UUID,
    db: DBSession,
):
    """Get a specific bot by ID."""
    service = BotService(db)
    bot = await service.get_bot(bot_id)
    return ApiResponse(success=True, data=bot, statusCode=status.HTTP_200_OK)


@router.patch("/{bot_id}", response_model=ApiResponse[BotResponse])
async def update_bot(
    bot_id: uuid.UUID,
    data: BotUpdate,
    db: DBSession,
):
    """Update a bot."""
    service = BotService(db)
    bot = await service.update_bot(bot_id, data)
    return ApiResponse(success=True, message="Bot updated successfully", data=bot, statusCode=status.HTTP_200_OK)


@router.delete("/{bot_id}", response_model=ApiResponse[None])
async def delete_bot(
    bot_id: uuid.UUID,
    db: DBSession,
):
    """Delete a bot and all its documents."""
    service = BotService(db)
    await service.delete_bot(bot_id)
    return ApiResponse(success=True, message="Bot deleted successfully", statusCode=status.HTTP_200_OK)
