"""
Integrations API — dynamic channel management.

Shared routes use {channel_type} path param so adding a new platform
requires zero route changes. Webhook routes remain platform-specific
because external services (Meta, Telegram) call them at fixed URLs.

POST   /setup/{channel_type}                — unified setup
GET    /status/{channel_type}/{bot_id}      — check channel status
DELETE /disconnect/{channel_type}/{bot_id}   — remove a channel
GET    /webhook/whatsapp                     — Meta webhook verification
POST   /webhook/whatsapp                     — WhatsApp incoming messages
POST   /webhook/telegram/{token_hash}        — Telegram incoming updates
"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.deps import CurrentUser, DBSession, OrgUser
from app.config import settings
from app.enums.channel import WebHookChannelType
from app.services.bot import BotService
from app.schemas.common import ApiResponse
from app.schemas.integration import (
    IntegrationSetupRequest,
    ChannelStatusResponse,
    WebhookInfoResponse,
)
from app.services.chat import ChatService
from app.services.integrations import IntegrationService
from app.services.integrations.whatsapp_provider import WhatsAppProvider
from app.services.permissions import PermissionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

integration_service = IntegrationService()


async def validated_setup(
    channel_type: WebHookChannelType,
    request: Request,
) -> IntegrationSetupRequest:
    """Merge path param (channel_type) with request body"""
    body = await request.json()
    body["channel_type"] = channel_type.value
    try:
        return IntegrationSetupRequest(**body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors())


# ======================================================================
# Dynamic channel routes
# ======================================================================


@router.post(
    "/setup/{channel_type}",
    response_model=ApiResponse[WebhookInfoResponse],
    dependencies=[Depends(PermissionService.Integrations.CREATE)],
)
async def channel_setup(
    channel_type: WebHookChannelType,
    db: DBSession,
    current_user: OrgUser,
    data: IntegrationSetupRequest = Depends(validated_setup),
):
    """Set up any supported integration. Request body is validated per channel type."""
    bot = await BotService(db).get_bot_or_raise(
        data.bot_id, organization_id=current_user.organization_id
    )

    result = await integration_service.setup(
        channel_type=channel_type,
        db=db,
        bot=bot,
        config=data.get_config(),
        base_url=settings.API_URL,
    )

    return ApiResponse(
        success=True,
        message=f"{channel_type.value.title()} integration configured successfully",
        data=WebhookInfoResponse(
            webhook_url=result.webhook_url,
            channel_type=channel_type.value,
            bot_id=data.bot_id,
        ),
    )


@router.get(
    "/status/{channel_type}/{bot_id}",
    response_model=ApiResponse[ChannelStatusResponse | None],
)
async def channel_status(
    channel_type: ChannelType,
    bot_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Check integration status for a bot on any supported channel."""
    channel = await integration_service.get_status(channel_type, db, bot_id)

    if not channel:
        return ApiResponse(success=True, data=None)

    return ApiResponse(
        success=True,
        data=ChannelStatusResponse(
            bot_id=bot_id,
            channel_type=channel_type.value,
            is_active=channel.is_active,
            created_at=channel.created_at,
        ),
    )


@router.delete(
    "/disconnect/{channel_type}/{bot_id}",
    response_model=ApiResponse,
    dependencies=[Depends(PermissionService.Integrations.DELETE)],
)
async def channel_disconnect(
    channel_type: ChannelType,
    bot_id: uuid.UUID,
    db: DBSession,
    current_user: OrgUser,
):
    """Disconnect any supported channel from a bot."""
    await integration_service.disconnect(channel_type, db, bot_id)
    return ApiResponse(success=True, message=f"{channel_type.value.title()} integration removed")


# ======================================================================
# Webhook routes — platform-specific (called by external services)
# ======================================================================


@router.get("/webhook/whatsapp")
async def whatsapp_verify_webhook(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    """Meta webhook verification (GET request)."""

    result = WhatsAppProvider.verify_subscription(mode, token, challenge)
    if result:
        return Response(content=result, media_type="text/plain")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Webhook verification failed",
    )


@router.post("/webhook/whatsapp")
async def whatsapp_incoming(payload: dict, db: DBSession):
    """Handle incoming WhatsApp messages."""

    provider = integration_service.get_provider(ChannelType.WHATSAPP)
    parsed = await provider.parse_incoming(payload)

    if not parsed:
        return {"status": "ok"}

    channel = await provider.get_active_channel(db)
    if not channel:
        logger.warning("[WhatsApp] No active WhatsApp channel found")
        return {"status": "no_bot"}

    bot = await BotService(db).get_bot_or_raise(
        channel.bot_id, require_active=True, raise_on_missing=False
    )
    if not bot:
        return {"status": "no_bot"}

    chat_service = ChatService(db)
    session_id = provider.make_session_id(parsed.sender_id)

    try:
        result = await chat_service.chat(
            bot_id=bot.id,
            message=parsed.message,
            organization_id=bot.organization_id,
            session_id=session_id,
        )
        await provider.send_reply(channel.channel_config, parsed.sender_id, result.message)
    except Exception as e:
        logger.error(f"[WhatsApp] Chat processing error: {e}")
        await provider.send_reply(
            channel.channel_config,
            parsed.sender_id,
            "Sorry, I encountered an error. Please try again.",
        )

    return {"status": "ok"}


@router.post("/webhook/telegram/{token_hash}")
async def telegram_incoming(
    token_hash: str,
    payload: dict,
    db: DBSession,
):
    """Handle incoming Telegram updates via webhook."""

    provider = integration_service.get_provider(ChannelType.TELEGRAM)
    parsed = await provider.parse_incoming(payload)
    if not parsed:
        return {"status": "ok"}

    channel = await provider.get_active_channel(db)
    if not channel:
        logger.warning("[Telegram] No active Telegram channel found")
        return {"status": "no_channel"}

    is_valid = await provider.verify_webhook(
        payload,
        token_hash=token_hash,
        channel_config=channel.channel_config,
    )
    if not is_valid:
        logger.warning("[Telegram] Token hash mismatch")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook token",
        )

    bot = await BotService(db).get_bot_or_raise(
        channel.bot_id, require_active=True, raise_on_missing=False
    )
    if not bot:
        return {"status": "no_bot"}

    chat_service = ChatService(db)
    session_id = provider.make_session_id(parsed.sender_id)

    try:
        result = await chat_service.chat(
            bot_id=bot.id,
            message=parsed.message,
            organization_id=bot.organization_id,
            session_id=session_id,
        )
        await provider.send_reply(channel.channel_config, parsed.sender_id, result.message)
    except Exception as e:
        logger.error(f"[Telegram] Chat processing error: {e}")
        await provider.send_reply(
            channel.channel_config,
            parsed.sender_id,
            "Sorry, I encountered an error. Please try again.",
        )

    return {"status": "ok"}
