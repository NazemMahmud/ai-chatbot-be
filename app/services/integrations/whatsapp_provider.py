"""
WhatsApp Business API integration provider.
"""
import hashlib
import hmac
import uuid
import logging

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums.channel import ChannelType
from app.models import BotChannel, Bot
from app.services.integrations.base import (
    BaseIntegrationProvider,
    ParsedMessage,
    SetupResult,
)

logger = logging.getLogger(__name__)


class WhatsAppProvider(BaseIntegrationProvider):
    channel_type = ChannelType.WHATSAPP

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
        config keys: phone_number_id, access_token, verify_token
        """
        existing = await db.execute(
            select(BotChannel).where(
                BotChannel.bot_id == bot.id,
                BotChannel.channel_type == self.channel_type.value,
            )
        )
        channel = existing.scalar_one_or_none()

        channel_config = {
            "phone_number_id": config["phone_number_id"],
            "access_token": config["access_token"],
            "verify_token": config["verify_token"],
        }

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

        webhook_url = f"{base_url}/api/integrations/whatsapp/webhook"
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
                detail="WhatsApp integration not found for this bot",
            )
        await db.delete(channel)
        await db.flush()

    # ------------------------------------------------------------------
    # Incoming message handling
    # ------------------------------------------------------------------

    async def parse_incoming(self, payload: dict) -> ParsedMessage | None:
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

            return ParsedMessage(
                sender_id=sender_phone,
                message=message_text,
                message_id=msg.get("id"),
            )
        except (IndexError, KeyError) as e:
            logger.error(f"[WhatsApp] Failed to parse webhook payload: {e}")
            return None

    async def verify_webhook(self, payload: dict, **kwargs) -> bool:
        """
        For WhatsApp, verification is done differently:
        - GET request verification uses mode/token/challenge (handled at route level)
        - POST request verification uses X-Hub-Signature-256
        """
        signature = kwargs.get("signature", "")
        payload_body = kwargs.get("payload_body", b"")

        if not signature or not settings.WHATSAPP_ACCESS_TOKEN:
            return False

        expected = hmac.new(
            settings.WHATSAPP_ACCESS_TOKEN.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    # ------------------------------------------------------------------
    # GET webhook verification (WhatsApp-specific, static)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_subscription(mode: str, token: str, challenge: str) -> str | None:
        """Verify webhook subscription from Meta. Returns challenge if valid."""
        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            logger.info("[WhatsApp] Webhook verified successfully")
            return challenge
        logger.warning("[WhatsApp] Webhook verification failed")
        return None

    # ------------------------------------------------------------------
    # Send reply
    # ------------------------------------------------------------------

    async def send_reply(
        self,
        channel_config: dict,
        recipient_id: str,
        text: str,
    ) -> bool:
        phone_number_id = channel_config.get("phone_number_id") or settings.WHATSAPP_PHONE_NUMBER_ID
        access_token = channel_config.get("access_token") or settings.WHATSAPP_ACCESS_TOKEN

        if not phone_number_id or not access_token:
            logger.error("[WhatsApp] Missing API credentials")
            return False

        url = f"{settings.WHATSAPP_API_URL}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "text",
            "text": {"body": text[:4096]},
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.info(f"[WhatsApp] Reply sent to {recipient_id}")
                return True
        except Exception as e:
            logger.error(f"[WhatsApp] Failed to send reply: {e}")
            return False
