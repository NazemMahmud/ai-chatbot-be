"""
WhatsApp Business API integration service.

Handles:
- Webhook verification for Meta
- Incoming message parsing
- Outbound message sending via WhatsApp Cloud API
"""
import hashlib
import hmac
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Bot, BotChannel
from app.services.bot import BotService

logger = logging.getLogger(__name__)


class WhatsAppService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Webhook verification (GET request from Meta)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_webhook(mode: str, token: str, challenge: str) -> str | None:
        """Verify webhook subscription from Meta. Returns challenge if valid."""
        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            logger.info("[WhatsApp] Webhook verified successfully")
            return challenge
        logger.warning("[WhatsApp] Webhook verification failed")
        return None

    # ------------------------------------------------------------------
    # Incoming message handling
    # ------------------------------------------------------------------

    async def handle_webhook(self, payload: dict) -> dict | None:
        """
        Parse incoming WhatsApp webhook payload.
        Returns dict with sender info and message text, or None if not a text message.
        """
        try:
            entry = payload.get("entry", [])
            if not entry:
                return None

            changes = entry[0].get("changes", [])
            if not changes:
                return None

            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if not messages:
                return None

            msg = messages[0]
            if msg.get("type") != "text":
                logger.info(f"[WhatsApp] Skipping non-text message type: {msg.get('type')}")
                return None

            sender_phone = msg.get("from", "")
            message_text = msg.get("text", {}).get("body", "")

            if not sender_phone or not message_text:
                return None

            return {
                "sender_phone": sender_phone,
                "message": message_text,
                "message_id": msg.get("id"),
            }
        except (IndexError, KeyError) as e:
            logger.error(f"[WhatsApp] Failed to parse webhook payload: {e}")
            return None

    # ------------------------------------------------------------------
    # Send reply
    # ------------------------------------------------------------------

    async def send_reply(self, phone_number: str, text: str) -> bool:
        """Send a text message reply via WhatsApp Cloud API."""
        if not settings.WHATSAPP_PHONE_NUMBER_ID or not settings.WHATSAPP_ACCESS_TOKEN:
            logger.error("[WhatsApp] Missing API credentials")
            return False

        url = (
            f"{settings.WHATSAPP_API_URL}"
            f"/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": text[:4096]},  # WhatsApp max message length
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.info(f"[WhatsApp] Reply sent to {phone_number}")
                return True
        except Exception as e:
            logger.error(f"[WhatsApp] Failed to send reply: {e}")
            return False

    # ------------------------------------------------------------------
    # Bot channel lookup
    # ------------------------------------------------------------------

    async def get_bot_for_channel(self) -> Bot | None:
        """Find the bot configured for WhatsApp channel."""
        result = await self.db.execute(
            select(BotChannel).where(
                BotChannel.channel_type == "whatsapp",
                BotChannel.is_active.is_(True),
            )
        )
        channel = result.scalar_one_or_none()
        if not channel:
            return None

        return await BotService(self.db).get_bot_or_raise(
            channel.bot_id,
            require_active=True,
            raise_on_missing=False,
        )

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    @staticmethod
    def verify_signature(payload_body: bytes, signature: str) -> bool:
        """Verify X-Hub-Signature-256 from Meta webhook."""
        if not signature or not settings.WHATSAPP_ACCESS_TOKEN:
            return False
        expected = hmac.new(
            settings.WHATSAPP_ACCESS_TOKEN.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
