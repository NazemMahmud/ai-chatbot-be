"""
Base integration provider — Strategy interface.

Every messaging platform (WhatsApp, Telegram, Discord, etc.) implements
this interface.  The IntegrationService facade dispatches to the correct
concrete provider based on ChannelType.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.channel import ChannelType
from app.models import Bot, BotChannel


@dataclass
class ParsedMessage:
    """Normalized incoming message from any platform."""

    sender_id: str          # platform-specific user identifier
    message: str            # text content
    message_id: str | None = None  # platform-specific message id
    raw: dict | None = None  # original payload fragment (for platform-specific needs)


@dataclass
class SetupResult:
    """Returned after a channel is set up."""

    channel: BotChannel
    webhook_url: str


class BaseIntegrationProvider(ABC):
    """Contract every integration provider must follow."""

    channel_type: ChannelType  # each subclass sets this

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    @abstractmethod
    async def setup(
        self,
        db: AsyncSession,
        bot: Bot,
        config: dict,
        base_url: str,
    ) -> SetupResult:
        """
        Configure the channel for the given bot.
        - Upsert BotChannel record
        - Do any platform registration (e.g. Telegram setWebhook)
        - Return SetupResult with the channel and webhook URL
        """

    @abstractmethod
    async def disconnect(
        self,
        db: AsyncSession,
        bot_id: uuid.UUID,
    ) -> None:
        """
        Remove the channel for the given bot.
        - Do any platform teardown (e.g. Telegram deleteWebhook)
        - Delete BotChannel record
        """

    # ------------------------------------------------------------------
    # Incoming message handling
    # ------------------------------------------------------------------

    @abstractmethod
    async def parse_incoming(self, payload: dict) -> ParsedMessage | None:
        """
        Parse a raw webhook payload into a ParsedMessage.
        Return None if the payload is not a processable text message.
        """

    @abstractmethod
    async def verify_webhook(self, payload: dict, **kwargs) -> bool:
        """
        Verify the authenticity of an incoming webhook request.
        Platform-specific (signature, token hash, etc.).
        Return True if valid.
        """

    # ------------------------------------------------------------------
    # Outbound messaging
    # ------------------------------------------------------------------

    @abstractmethod
    async def send_reply(
        self,
        channel_config: dict,
        recipient_id: str,
        text: str,
    ) -> bool:
        """Send a text reply to the given recipient via the platform API."""

    # ------------------------------------------------------------------
    # Channel lookup (shared default — override only if needed)
    # ------------------------------------------------------------------

    async def get_active_channel(
        self,
        db: AsyncSession,
        bot_id: uuid.UUID | None = None,
    ) -> BotChannel | None:
        """Find the active BotChannel for this provider's channel_type."""
        from sqlalchemy import select

        filters = [
            BotChannel.channel_type == self.channel_type.value,
            BotChannel.is_active.is_(True),
        ]
        if bot_id is not None:
            filters.append(BotChannel.bot_id == bot_id)

        result = await db.execute(select(BotChannel).where(*filters))
        return result.scalar_one_or_none()

    async def get_status(
        self,
        db: AsyncSession,
        bot_id: uuid.UUID,
    ) -> BotChannel | None:
        """Get channel status for a bot (active or not)."""
        from sqlalchemy import select

        result = await db.execute(
            select(BotChannel).where(
                BotChannel.bot_id == bot_id,
                BotChannel.channel_type == self.channel_type.value,
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def session_id_prefix(self) -> str:
        """Prefix for session IDs to isolate conversations by channel."""
        prefixes = {
            ChannelType.WHATSAPP: "wa",
            ChannelType.TELEGRAM: "tg",
            ChannelType.WIDGET: "wgt",
        }
        return prefixes.get(self.channel_type, self.channel_type.value)

    def make_session_id(self, sender_id: str) -> str:
        """Build a channel-scoped session ID."""
        return f"{self.session_id_prefix()}-{sender_id}"
