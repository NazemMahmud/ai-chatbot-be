"""
Integration facade — single entry point for all messaging integrations.

Routes operations to the correct provider based on WebHookChannelType.
To add a new platform (e.g. Discord), create a provider class and
register it in _PROVIDERS.
"""
import uuid
import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.channel import WebHookChannelType
from app.models import Bot, BotChannel
from app.services.integrations.base import (
    BaseIntegrationProvider,
    ParsedMessage,
    SetupResult,
)
from app.services.integrations.whatsapp_provider import WhatsAppProvider
from app.services.integrations.telegram_provider import TelegramProvider

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Provider registry — add new platforms here
# ------------------------------------------------------------------

_PROVIDERS: dict[WebHookChannelType, BaseIntegrationProvider] = {
    WebHookChannelType.WHATSAPP: WhatsAppProvider(),
    WebHookChannelType.TELEGRAM: TelegramProvider(),
}


class IntegrationService:
    """
    Facade that delegates to the correct provider.

    Usage:
        service = IntegrationService()
        provider = service.get_provider(WebHookChannelType.WHATSAPP)
        # or use the convenience methods directly:
        result = await service.setup(WebHookChannelType.WHATSAPP, db, bot, config, base_url)
    """

    @staticmethod
    def get_provider(channel_type: WebHookChannelType) -> BaseIntegrationProvider:
        """Get the provider instance for the given channel type."""
        provider = _PROVIDERS.get(channel_type)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported channel type: {channel_type.value}",
            )
        return provider

    @staticmethod
    def supported_channels() -> list[str]:
        """List all registered channel types."""
        return [ct.value for ct in _PROVIDERS]

    # ------------------------------------------------------------------
    # Delegating convenience methods
    # ------------------------------------------------------------------

    async def setup(
        self,
        channel_type: WebHookChannelType,
        db: AsyncSession,
        bot: Bot,
        config: dict,
        base_url: str,
    ) -> SetupResult:
        provider = self.get_provider(channel_type)
        return await provider.setup(db, bot, config, base_url)

    async def disconnect(
        self,
        channel_type: WebHookChannelType,
        db: AsyncSession,
        bot_id: uuid.UUID,
    ) -> None:
        provider = self.get_provider(channel_type)
        await provider.disconnect(db, bot_id)

    async def get_status(
        self,
        channel_type: WebHookChannelType,
        db: AsyncSession,
        bot_id: uuid.UUID,
    ) -> BotChannel | None:
        provider = self.get_provider(channel_type)
        return await provider.get_status(db, bot_id)

    async def parse_incoming(
        self,
        channel_type: WebHookChannelType,
        payload: dict,
    ) -> ParsedMessage | None:
        provider = self.get_provider(channel_type)
        return await provider.parse_incoming(payload)

    async def send_reply(
        self,
        channel_type: WebHookChannelType,
        channel_config: dict,
        recipient_id: str,
        text: str,
    ) -> bool:
        provider = self.get_provider(channel_type)
        return await provider.send_reply(channel_config, recipient_id, text)

    async def get_active_channel(
        self,
        channel_type: WebHookChannelType,
        db: AsyncSession,
        bot_id: uuid.UUID | None = None,
    ) -> BotChannel | None:
        provider = self.get_provider(channel_type)
        return await provider.get_active_channel(db, bot_id)
