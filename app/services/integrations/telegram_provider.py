"""
Telegram Bot API integration provider.
"""
import hashlib
import uuid
import logging

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.channel import ChannelType
from app.models import BotChannel, Bot
from app.services.integrations.base import (
    BaseIntegrationProvider,
    ParsedMessage,
    SetupResult,
)

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramProvider(BaseIntegrationProvider):
    channel_type = ChannelType.TELEGRAM

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def setup(
        self,
        db: AsyncSession,
        bot: Bot,
        config: dict,
        base_url: str,
    ) -> SetupResult:
        """
        config keys: bot_token
        """
        bot_token = config["bot_token"]

        # Generate webhook URL with token hash for security
        token_hash = hashlib.sha256(bot_token.encode()).hexdigest()[:16]
        webhook_url = f"{base_url}/api/integrations/telegram/webhook/{token_hash}"

        # Register webhook with Telegram first
        success = await self._set_webhook(bot_token, webhook_url)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to register webhook with Telegram. Check your bot token.",
            )

        # Upsert BotChannel
        from sqlalchemy import select

        existing = await db.execute(
            select(BotChannel).where(
                BotChannel.bot_id == bot.id,
                BotChannel.channel_type == self.channel_type.value,
            )
        )
        channel = existing.scalar_one_or_none()

        channel_config = {"bot_token": bot_token}

        if channel:
            channel.channel_config = channel_config
            channel.is_active = True
        else:
            channel = BotChannel(
                bot_id=bot.id,
                channel_type=self.channel_type.value,
                channel_config=channel_config,
                is_active=True,
            )
            db.add(channel)

        await db.flush()
        return SetupResult(channel=channel, webhook_url=webhook_url)

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------

    async def disconnect(
        self,
        db: AsyncSession,
        bot_id: uuid.UUID,
    ) -> None:
        channel = await self.get_status(db, bot_id)
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Telegram integration not found for this bot",
            )

        # Remove webhook from Telegram
        bot_token = channel.channel_config.get("bot_token", "")
        if bot_token:
            await self._delete_webhook(bot_token)

        await db.delete(channel)
        await db.flush()

    # ------------------------------------------------------------------
    # Incoming message handling
    # ------------------------------------------------------------------

    async def parse_incoming(self, payload: dict) -> ParsedMessage | None:
        message = payload.get("message")
        if not message:
            return None

        text = message.get("text")
        if not text:
            return None

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if not chat_id:
            return None

        return ParsedMessage(
            sender_id=str(chat_id),
            message=text,
            message_id=str(message.get("message_id", "")),
            raw={"from_user": message.get("from", {})},
        )

    async def verify_webhook(self, payload: dict, **kwargs) -> bool:
        """
        Verify that the token_hash in the URL matches the stored bot_token.
        """
        token_hash = kwargs.get("token_hash", "")
        channel_config = kwargs.get("channel_config", {})
        bot_token = channel_config.get("bot_token", "")

        if not token_hash or not bot_token:
            return False

        expected_hash = hashlib.sha256(bot_token.encode()).hexdigest()[:16]
        return token_hash == expected_hash

    # ------------------------------------------------------------------
    # Send reply
    # ------------------------------------------------------------------

    async def send_reply(
        self,
        channel_config: dict,
        recipient_id: str,
        text: str,
    ) -> bool:
        bot_token = channel_config.get("bot_token", "")
        if not bot_token:
            logger.error("[Telegram] Missing bot_token in channel config")
            return False

        url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
        send_payload = {
            "chat_id": recipient_id,
            "text": text[:4096],
            "parse_mode": "Markdown",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=send_payload)
                if response.status_code == 400:
                    # Markdown parse failed, retry without parse_mode
                    send_payload.pop("parse_mode")
                    response = await client.post(url, json=send_payload)
                response.raise_for_status()
                logger.info(f"[Telegram] Reply sent to chat_id={recipient_id}")
                return True
        except Exception as e:
            logger.error(f"[Telegram] Failed to send reply: {e}")
            return False

    # ------------------------------------------------------------------
    # Telegram-specific helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_webhook(bot_token: str, webhook_url: str) -> bool:
        """Register a webhook URL with Telegram Bot API."""
        url = f"{TELEGRAM_API_BASE}/bot{bot_token}/setWebhook"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json={"url": webhook_url})
                response.raise_for_status()
                data = response.json()
                if data.get("ok"):
                    logger.info(f"[Telegram] Webhook set successfully: {webhook_url}")
                    return True
                logger.error(f"[Telegram] setWebhook failed: {data}")
                return False
        except Exception as e:
            logger.error(f"[Telegram] setWebhook error: {e}")
            return False

    @staticmethod
    async def _delete_webhook(bot_token: str) -> bool:
        """Remove the webhook from Telegram Bot API."""
        url = f"{TELEGRAM_API_BASE}/bot{bot_token}/deleteWebhook"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url)
                response.raise_for_status()
                logger.info("[Telegram] Webhook deleted")
                return True
        except Exception as e:
            logger.error(f"[Telegram] deleteWebhook error: {e}")
            return False
