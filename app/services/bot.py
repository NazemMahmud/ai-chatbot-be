import uuid
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bot
from app.schemas.bot import BotCreate, BotUpdate, BotListData, BotPickerListData


class BotService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_bot_or_raise(
        self,
        bot_id: uuid.UUID,
        *,
        organization_id: uuid.UUID | None = None,
        require_active: bool = False,
        raise_on_missing: bool = True,
    ) -> Bot | None:
        """        Reusable bot lookup with dynamic filters.    """
        filters = [Bot.id == bot_id, Bot.deleted_at.is_(None)]

        if organization_id is not None:
            filters.append(Bot.organization_id == organization_id)

        if require_active:
            filters.append(Bot.is_active.is_(True))

        result = await self.db.execute(select(Bot).where(*filters))
        bot = result.scalar_one_or_none()

        if not bot and raise_on_missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found",
            )

        return bot

    @staticmethod
    def check_origin(request: Request, bot: Bot) -> None:
        """
        Validate the request origin against the bot's allowed_domains list.

        Rules:
          1. No allowed_domains set → allow all origins.
          2. No origin/referer header → allow (server-to-server calls).
          3. Origin matches an allowed domain (wildcard supported) → allow.
          4. Otherwise → raise 403 Forbidden.
        """
        if not bot.allowed_domains:
            return

        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")
        check_value = origin or referer

        if not check_value:
            return

        domain = (
            check_value
            .replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
            .split(":")[0]
        )

        for allowed in bot.allowed_domains:
            allowed_clean = allowed.strip().lower()
            if not allowed_clean:
                continue
            if allowed_clean.startswith("*."):
                if domain.endswith(allowed_clean[1:]) or domain == allowed_clean[2:]:
                    return
            elif domain == allowed_clean:
                return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This domain is not authorized to use this widget",
        )

    async def get_bot(self, bot_id: uuid.UUID, organization_id: uuid.UUID) -> Bot:
        return await self.get_bot_or_raise(
            bot_id, organization_id=organization_id
        )

    async def create_bot(self, bot: BotCreate, organization_id: uuid.UUID) -> Bot:
        # Serialize WidgetConfig to plain dict so only known keys hit the DB
        widget_config = (
            bot.widget_config.model_dump(mode="json") if bot.widget_config else None
        )

        bot_kwargs = dict(
            name=bot.name,
            description=bot.description,
            system_prompt=bot.system_prompt,
            welcome_message=bot.welcome_message,
            is_active=True,
            allowed_domains=bot.allowed_domains,
            organization_id=organization_id,
        )
        # Only set widget_config explicitly when provided — if None, let the
        # server_default (jsonb_build_object) apply so the JSONB key-deletion
        # check constraints never see a JSON null scalar.
        if widget_config is not None:
            bot_kwargs["widget_config"] = widget_config

        db_bot = Bot(**bot_kwargs)
        self.db.add(db_bot)
        await self.db.flush()
        await self.db.refresh(db_bot)
        return db_bot

    async def list_bots(
        self,
        organization_id: uuid.UUID,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> BotListData:
        query = select(Bot).where(
            Bot.organization_id == organization_id,
            Bot.deleted_at.is_(None),
        )

        if is_active is not None:
            query = query.where(Bot.is_active == is_active)

        query = query.order_by(Bot.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        bots = list(result.scalars().all())

        return BotListData(data=bots)

    async def search_bots_for_picker(
        self,
        organization_id: uuid.UUID,
        search: Optional[str] = None
    ) -> BotPickerListData:
        """
        Lightweight bot list for picker/select components (documents page).

        Returns only id + name of active bots.
        If search is provided, filters by bot name (case-insensitive ILIKE).
        Limit is configurable (default 20, will be tied to subscription later).
        """
        limit: int = 20 # TODO: configurable based on subscription package later.
        query = select(Bot.id, Bot.name).where(
            Bot.organization_id == organization_id,
            Bot.is_active.is_(True),
            Bot.deleted_at.is_(None),
        )

        if search and search.strip():
            query = query.where(Bot.name.ilike(f"%{search.strip()}%"))

        query = query.order_by(Bot.name.asc()).limit(limit)

        result = await self.db.execute(query)
        rows = result.all()

        return BotPickerListData(
            data=[{"id": row.id, "name": row.name} for row in rows]
        )

    async def update_bot(
        self, bot_id: uuid.UUID, data: BotUpdate, organization_id: uuid.UUID
    ) -> Bot:
        bot = await self.get_bot(bot_id, organization_id)

        update_data = data.model_dump(exclude_unset=True)

        # Serialize WidgetConfig to plain dict so only known keys hit the DB
        if "widget_config" in update_data and update_data["widget_config"] is not None:
            update_data["widget_config"] = data.widget_config.model_dump(mode="json")

        for key, value in update_data.items():
            setattr(bot, key, value)

        await self.db.flush()
        await self.db.refresh(bot)
        return bot

    async def delete_bot(self, bot_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        bot = await self.get_bot(bot_id, organization_id)

        bot.soft_delete()
        await self.db.flush()

        return True
