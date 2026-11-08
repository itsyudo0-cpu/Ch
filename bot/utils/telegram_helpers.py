from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramRetryAfter,
)
from aiogram.types import (
    ChatMemberAdministrator,
    ChatMemberOwner,
    Message,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(slots=True)
class ChannelVerificationResult:
    ok: bool
    channel_id: int = 0
    title: str = ""
    username: str | None = None
    error_message: str = ""


def extract_post_metadata(message: Message) -> tuple[str, str] | None:
    """
    Determine supported content_type and a human-readable text preview from a message.
    Supported types: text, photo, video, document, animation (GIF), audio, voice.
    """
    raw_text = message.text or message.caption or ""
    preview = " ".join(raw_text.split())[:80]

    if message.text:
        return ("text", preview or "(Text post)")
    if message.photo:
        return ("photo", preview or "(Photo post)")
    if message.video:
        return ("video", preview or "(Video post)")
    if message.animation:
        return ("animation", preview or "(GIF / Animation post)")
    if message.document:
        doc_name = message.document.file_name or "Document"
        return ("document", preview or f"({doc_name})")
    if message.audio:
        audio_title = message.audio.title or message.audio.file_name or "Audio"
        return ("audio", preview or f"({audio_title})")
    if message.voice:
        return ("voice", preview or "(Voice message)")

    return None


def format_telegram_error(exc: Exception) -> str:
    """Translate Telegram API exceptions into clear, actionable error messages."""
    if isinstance(exc, TelegramRetryAfter):
        return (
            f"Telegram rate limit hit (HTTP 429). "
            f"Please wait {exc.retry_after} seconds before trying again."
        )
    if isinstance(exc, TelegramForbiddenError):
        msg = str(exc).lower()
        if "kicked" in msg:
            return "The bot was kicked from the channel. Please re-add the bot as an administrator."
        return (
            "Access forbidden: The bot is no longer an administrator in this channel "
            "or lacks required permissions."
        )
    if isinstance(exc, (TelegramNotFound, TelegramBadRequest)):
        msg = str(exc).lower()
        if "chat not found" in msg:
            return (
                "Channel not found. Make sure the @username is correct and the bot "
                "has been added to the channel as an administrator."
            )
        if "not enough rights" in msg or "need administrator rights" in msg:
            return (
                "The bot does not have enough administrator rights in the channel. "
                "Please enable 'Post Messages' and 'Edit Messages of Others'."
            )
        if "message to edit not found" in msg or "message to delete not found" in msg:
            return "The published message was not found in the channel (it may have already been deleted)."
        if "message is not modified" in msg:
            return "The buttons are identical to the ones already on the post."
        return f"Telegram rejected the request: {exc.message}"
    if isinstance(exc, TelegramAPIError):
        return f"Telegram API error: {exc}"
    return f"Unexpected error: {exc}"


async def call_with_retry_after(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    max_auto_wait: int = 5,
    **kwargs: Any,
) -> T:
    """
    Execute a Telegram Bot API call. If HTTP 429 (TelegramRetryAfter) occurs and
    retry_after <= max_auto_wait seconds, sleep and retry once automatically;
    otherwise re-raise so the handler can report the exact wait duration.
    """
    try:
        return await func(*args, **kwargs)
    except TelegramRetryAfter as exc:
        logger.warning("Rate limited by Telegram: retry_after=%ss", exc.retry_after)
        if exc.retry_after <= max_auto_wait:
            await asyncio.sleep(exc.retry_after)
            return await func(*args, **kwargs)
        raise


async def verify_channel_and_permissions(
    bot: Bot,
    target_chat_id_or_username: int | str,
    user_id: int,
) -> ChannelVerificationResult:
    """
    Verify that:
    1. The target chat exists and is a Telegram channel.
    2. The bot is an administrator in the channel with `can_post_messages` and `can_edit_messages`.
    3. The requesting user is the channel creator (`creator`) or an administrator (`administrator`).
    """
    try:
        chat = await call_with_retry_after(bot.get_chat, target_chat_id_or_username)
    except Exception as exc:
        return ChannelVerificationResult(
            ok=False,
            error_message=format_telegram_error(exc),
        )

    if chat.type != ChatType.CHANNEL:
        return ChannelVerificationResult(
            ok=False,
            error_message="The specified chat is not a Telegram channel. Please provide a broadcast channel.",
        )

    bot_info = await bot.get_me()

    # 1. Check bot membership and post/edit permissions
    try:
        bot_member = await call_with_retry_after(
            bot.get_chat_member, chat_id=chat.id, user_id=bot_info.id
        )
    except Exception as exc:
        return ChannelVerificationResult(
            ok=False,
            error_message=(
                "Could not verify bot permissions in the channel. "
                f"Ensure @{bot_info.username} is added as a channel administrator.\n"
                f"Details: {format_telegram_error(exc)}"
            ),
        )

    if bot_member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return ChannelVerificationResult(
            ok=False,
            error_message=(
                f"@{bot_info.username} is not an administrator in '{chat.title}'. "
                "Please add the bot as a Channel Administrator first."
            ),
        )

    if isinstance(bot_member, ChatMemberAdministrator):
        can_post = bool(bot_member.can_post_messages)
        can_edit = bool(bot_member.can_edit_messages)
        if not can_post or not can_edit:
            missing: list[str] = []
            if not can_post:
                missing.append("Post Messages")
            if not can_edit:
                missing.append("Edit Messages")
            return ChannelVerificationResult(
                ok=False,
                error_message=(
                    f"@{bot_info.username} is missing required admin permissions in '{chat.title}': "
                    f"{', '.join(missing)}. Please enable them in Channel Settings -> Administrators."
                ),
            )

    # 2. Check user membership (must be creator or administrator)
    try:
        user_member = await call_with_retry_after(
            bot.get_chat_member, chat_id=chat.id, user_id=user_id
        )
    except Exception as exc:
        return ChannelVerificationResult(
            ok=False,
            error_message=(
                "Could not verify your membership in the channel. "
                f"Details: {format_telegram_error(exc)}"
            ),
        )

    if not isinstance(user_member, (ChatMemberOwner, ChatMemberAdministrator)) and (
        user_member.status not in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}
    ):
        return ChannelVerificationResult(
            ok=False,
            error_message=(
                f"You must be the creator or an administrator of '{chat.title}' "
                "to connect it to this bot."
            ),
        )

    return ChannelVerificationResult(
        ok=True,
        channel_id=chat.id,
        title=chat.title or str(chat.id),
        username=chat.username,
    )
