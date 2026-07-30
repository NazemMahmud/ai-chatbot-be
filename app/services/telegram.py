"""
Telegram Bot API integration service.

Handles:
- Webhook registration with Telegram
- Incoming update parsing
- Outbound message sending
"""
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Bot, BotChannel

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Webhook management
    # ------------------------------------------------------------------

    @staticmethod
    async def set_webhook(bot_token: str, webhook_url: str) -> bool:
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
    async def delete_webhook(bot_token: str) -> bool:
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

    # ------------------------------------------------------------------
    # Incoming update handling
    # ------------------------------------------------------------------

    @staticmethod
    def parse_update(payload: dict) -> dict | None:
        """
        Parse incoming Telegram Update.
        Returns dict with chat_id and message text, or None if not a text message.
        """
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

        return {
            "chat_id": chat_id,
            "message": text,
            "message_id": message.get("message_id"),
            "from_user": message.get("from", {}),
        }

    # ------------------------------------------------------------------
    # Send reply
    # ------------------------------------------------------------------

    @staticmethod
    async def send_reply(bot_token: str, chat_id: int, text: str) -> bool:
        """Send a text message reply via Telegram Bot API."""
        url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text[:4096],  # Telegram max message length
            "parse_mode": "Markdown",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 400:
                    # Markdown parse failed, retry without parse_mode
                    payload.pop("parse_mode")
                    response = await client.post(url, json=payload)
                response.raise_for_status()
                logger.info(f"[Telegram] Reply sent to chat_id={chat_id}")
                return True
        except Exception as e:
            logger.error(f"[Telegram] Failed to send reply: {e}")
            return False

    # ------------------------------------------------------------------
    # Bot channel lookup
    # ------------------------------------------------------------------

    async def get_channel_for_bot(self, bot_id) -> BotChannel | None:
        """Find the Telegram channel config for a bot."""
        result = await self.db.execute(
            select(BotChannel).where(
                BotChannel.bot_id == bot_id,
                BotChannel.channel_type == "telegram",
                BotChannel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_telegram_channel(self) -> BotChannel | None:
        """Find any active Telegram channel (for webhook routing)."""
        result = await self.db.execute(
            select(BotChannel).where(
                BotChannel.channel_type == "telegram",
                BotChannel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()
