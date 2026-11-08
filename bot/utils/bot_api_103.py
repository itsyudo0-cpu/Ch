"""
Optional helpers for Telegram Bot API 10.3 (Aug 24, 2026):
Rich Message buttons (RichMessageButton / RichBlockButtons) and
Ephemeral Messages (EphemeralMessageParameters).

aiogram 3.x does not ship these types yet, so they are sent as raw API
methods. Everything here is OPT-IN (VOTE_EPHEMERAL_CARD=true) and the vote
flow always falls back to the classic answerCallbackQuery toast on any error.

NOTE: field names follow the public Bot API 10.3 docs. Ephemeral messages are
documented for groups; whether a channel-post callback can receive one is
decided by Telegram's servers, hence the fallback.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.methods import TelegramMethod

RICH_BUTTON_STYLES = frozenset({"danger", "success", "primary"})
MAX_RICH_BUTTONS_PER_BLOCK = 8
VALID_ALIGN = frozenset({"left", "center", "right"})


def rich_callback_button(
    text: str, callback_data: str, style: str | None = None
) -> dict[str, Any]:
    """RichMessageButton with a callback action (exactly one action is allowed)."""
    if not 1 <= len(callback_data.encode("utf-8")) <= 64:
        raise ValueError("callback_data must be 1-64 bytes")
    if style is not None and style not in RICH_BUTTON_STYLES:
        raise ValueError(f"style must be one of {sorted(RICH_BUTTON_STYLES)}")
    button: dict[str, Any] = {"text": text, "callback_data": callback_data}
    if style:
        button["style"] = style
    return button


def rich_buttons_block(
    buttons: list[dict[str, Any]], align: str = "left"
) -> dict[str, Any]:
    """InputRichBlockButtons: one row of 1-8 RichMessageButton."""
    if not 1 <= len(buttons) <= MAX_RICH_BUTTONS_PER_BLOCK:
        raise ValueError("A buttons block needs 1-8 buttons")
    if align not in VALID_ALIGN:
        raise ValueError("align must be left, center or right")
    return {"type": "buttons", "buttons": buttons, "align": align}


def ephemeral_parameters(
    receiver_user_id: int,
    callback_query_id: str | None = None,
    replace_callback_query_message: bool = False,
) -> dict[str, Any]:
    """EphemeralMessageParameters: message visible only to one user (+ the bot)."""
    params: dict[str, Any] = {"receiver_user_id": receiver_user_id}
    if callback_query_id:
        params["callback_query_id"] = callback_query_id
    if replace_callback_query_message:
        params["replace_callback_query_message"] = True
    return params


class SendRichMessage(TelegramMethod[Any]):
    """Raw `sendRichMessage` (Bot API 10.1+, ephemeral parameters in 10.3)."""

    __returning__ = Any
    __api_method__ = "sendRichMessage"

    chat_id: int | str
    rich_message: dict[str, Any]
    disable_notification: bool | None = None
    protect_content: bool | None = None
    ephemeral_message_parameters: dict[str, Any] | None = None


class EditRichMessageText(TelegramMethod[Any]):
    """`editMessageText` with the `rich_message` parameter (no separate edit method exists)."""

    __returning__ = Any
    __api_method__ = "editMessageText"

    chat_id: int | str
    message_id: int
    rich_message: dict[str, Any]


def _message_id(result: Any) -> int:
    if isinstance(result, dict):
        return int(result["message_id"])
    return int(getattr(result, "message_id"))


async def send_rich_post(
    bot: Bot,
    chat_id: int | str,
    rich_message: dict[str, Any],
    silent: bool = False,
    protect_content: bool = False,
) -> int:
    """Send a rich message (channel post / preview). Returns the new message_id."""
    result = await bot(
        SendRichMessage(
            chat_id=chat_id,
            rich_message=rich_message,
            disable_notification=silent or None,
            protect_content=protect_content or None,
        )
    )
    return _message_id(result)


async def edit_rich_post(
    bot: Bot, chat_id: int | str, message_id: int, rich_message: dict[str, Any]
) -> None:
    await bot(
        EditRichMessageText(
            chat_id=chat_id, message_id=message_id, rich_message=rich_message
        )
    )


async def send_personal_vote_card(
    bot: Bot,
    chat_id: int,
    user_id: int,
    callback_query_id: str,
    buttons: list[dict[str, Any]],
) -> None:
    """Show a rich button card that only `user_id` can see (own choice highlighted)."""
    await bot(
        SendRichMessage(
            chat_id=chat_id,
            rich_message={"blocks": [rich_buttons_block(buttons)]},
            ephemeral_message_parameters=ephemeral_parameters(
                receiver_user_id=user_id, callback_query_id=callback_query_id
            ),
        )
    )
