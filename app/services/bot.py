import uuid

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bot import Bot
from app.models.organization import Organization
from app.schemas.bot import BotCreate, BotUpdate


class BotService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _verify_org_access(self, org_id: uuid.UUID, user_id: uuid.UUID) -> Organization:
        """Verify user has access to the org."""
        result = await self.db.execute(
            select(Organization).where(
                Organization.id == org_id, Organization.owner_id == user_id
            )
        )
        org = result.scalar_one_or_none()
        if not org:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No access to this organization"
            )
        return org

    async def list_bots(self, org_id: uuid.UUID, user_id: uuid.UUID) -> list[Bot]:
        await self._verify_org_access(org_id, user_id)
        result = await self.db.execute(select(Bot).where(Bot.org_id == org_id))
        return list(result.scalars().all())

    async def create_bot(
        self, org_id: uuid.UUID, data: BotCreate, user_id: uuid.UUID
    ) -> Bot:
        await self._verify_org_access(org_id, user_id)

        bot = Bot(
            org_id=org_id,
            name=data.name,
            slug=slugify(data.name),
            system_prompt=data.system_prompt,
            welcome_message=data.welcome_message,
            model=data.model,
            temperature=data.temperature,
            show_citations=data.show_citations,
            allowed_domains=data.allowed_domains,
        )
        self.db.add(bot)
        await self.db.flush()
        await self.db.refresh(bot)
        return bot

    async def get_bot(self, bot_id: uuid.UUID, user_id: uuid.UUID) -> Bot | None:
        result = await self.db.execute(select(Bot).where(Bot.id == bot_id))
        bot = result.scalar_one_or_none()
        if bot:
            await self._verify_org_access(bot.org_id, user_id)
        return bot

    async def update_bot(
        self, bot_id: uuid.UUID, data: BotUpdate, user_id: uuid.UUID
    ) -> Bot | None:
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(bot, field, value)

        await self.db.flush()
        await self.db.refresh(bot)
        return bot

    async def delete_bot(self, bot_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return False
        await self.db.delete(bot)
        await self.db.flush()
        return True
