from __future__ import annotations

from typing import Any

from aiogram import Bot

from bot.db import PostRecord
from bot.utils.bot_api_103 import edit_rich_post
from bot.utils.button_parser import build_inline_keyboard
from bot.utils.rich_post import build_rich_message
from bot.utils.telegram_helpers import call_with_retry_after


async def push_post_buttons(
    bot: Bot,
    post: PostRecord,
    rows: list[list[dict[str, str]]],
    vote_token: str | None,
    vote_counts: dict[str, int] | None,
) -> None:
    """
    Update the buttons of an already published channel post.

    Rich posts (Bot API 10.3): rebuild the rich message and edit it with
    `editMessageText(rich_message=...)`. Classic posts: `editMessageReplyMarkup`.
    """
    content: dict[str, Any] | None = post.rich_content
    if content is not None:
        await call_with_retry_after(
            edit_rich_post,
            bot,
            post.channel_id,
            post.channel_message_id,
            build_rich_message(content, rows, vote_token, vote_counts),
        )
        return

    await call_with_retry_after(
        bot.edit_message_reply_markup,
        chat_id=post.channel_id,
        message_id=post.channel_message_id,
        reply_markup=build_inline_keyboard(
            rows, vote_token=vote_token, vote_counts=vote_counts
        ),
    )
