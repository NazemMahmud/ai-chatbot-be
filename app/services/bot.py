import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bot
from app.schemas.bot import BotCreate, BotUpdate, BotListData

class BotService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_bot(self, bot: BotCreate) -> Bot:
        bot = Bot(
            name=bot.name,
            description=bot.description,
            is_active=True,
        )
        self.db.add(bot)
        await self.db.flush()
        await self.db.refresh(bot)
        return bot
    
    
    async def list_bots(self, is_active: Optional[bool] = None, limit: int = 50, offset: int = 0) -> BotListData:
        """
        List bots with optional filtering by is_active status.
        Returns paginated results sorted by created_at descending.
        """
        query = select(Bot)
        # count_query = select(func.count()).select_from(Bot)

        if is_active is not None:
            query = query.where(Bot.is_active == is_active)
            # count_query = count_query.where(Bot.is_active == is_active)

        query = query.order_by(Bot.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        bots = list(result.scalars().all())

        # count_result = await self.db.execute(count_query)
        # total = count_result.scalar()

        return BotListData(data=bots)
        # return BotListData(bots=bots, total=total)
    
    async def get_bot(self, bot_id: uuid.UUID) -> Bot:
        """Get a specific bot by ID."""
        result = await self.db.execute(select(Bot).where(Bot.id == bot_id))
        bot = result.scalar_one_or_none()

        if not bot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")

        return bot

    
    async def update_bot(self, bot_id: uuid.UUID, data: BotUpdate) -> Bot:
        """Update a bot with provided fields."""
        bot = await self.get_bot(bot_id)
        
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(bot, key, value)

        await self.db.flush()
        await self.db.refresh(bot)
        return bot
    
    async def delete_bot(self, bot_id: uuid.UUID) -> bool:
        """Delete a bot and all its documents."""
        bot = await self.get_bot(bot_id)

        await self.db.delete(bot)
        await self.db.flush()

        return True