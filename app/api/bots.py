import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.bot import BotCreate, BotListResponse, BotResponse, BotUpdate
from app.services.bot import BotService

router = APIRouter()


@router.get("/orgs/{org_id}/bots", response_model=list[BotListResponse])
async def list_bots(org_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    service = BotService(db)
    return await service.list_bots(org_id, current_user.id)


@router.post(
    "/orgs/{org_id}/bots", response_model=BotResponse, status_code=status.HTTP_201_CREATED
)
async def create_bot(org_id: uuid.UUID, data: BotCreate, db: DBSession, current_user: CurrentUser):
    service = BotService(db)
    return await service.create_bot(org_id, data, current_user.id)


@router.get("/bots/{bot_id}", response_model=BotResponse)
async def get_bot(bot_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    service = BotService(db)
    bot = await service.get_bot(bot_id, current_user.id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    return bot


@router.patch("/bots/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: uuid.UUID, data: BotUpdate, db: DBSession, current_user: CurrentUser
):
    service = BotService(db)
    bot = await service.update_bot(bot_id, data, current_user.id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    return bot


@router.delete("/bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(bot_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    service = BotService(db)
    deleted = await service.delete_bot(bot_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
