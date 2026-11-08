from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from bot.config import Settings
from bot.db import Database, PostRecord
from bot.utils.button_parser import (
    PREVIEW_VOTE_TOKEN,
    VOTE_CALLBACK_PREFIX,
    build_vote_callback,
    is_vote_button,
    parse_vote_callback,
)
from bot.utils.post_render import push_post_buttons

logger = logging.getLogger(__name__)
router = Router(name="votes")

# Keyboard refreshes are coalesced: many votes in a short time -> one edit.
REFRESH_DELAY_SECONDS = 1.2
_pending_refresh: set[str] = set()
_background_tasks: set[asyncio.Task[None]] = set()


def _find_vote_label(post: PostRecord, option_id: str) -> str | None:
    for row in post.buttons:
        for btn in row:
            if is_vote_button(btn) and btn["vote"] == option_id:
                return btn["text"]
    return None


async def refresh_post_keyboard(bot: Bot, db: Database, post: PostRecord) -> None:
    """Rewrite the live counters on the channel post's inline keyboard."""
    token = post.vote_token
    if not token:
        return
    counts = await db.get_vote_counts(token)
    try:
        await push_post_buttons(bot, post, post.buttons, token, counts)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning("Vote counter refresh failed for post #%s: %s", post.id, exc)
    except Exception as exc:  # network / rights problems must never break voting
        logger.warning("Vote counter refresh failed for post #%s: %s", post.id, exc)


def schedule_refresh(bot: Bot, db: Database, post: PostRecord) -> None:
    token = post.vote_token
    if not token or token in _pending_refresh:
        return
    _pending_refresh.add(token)

    async def _run() -> None:
        try:
            await asyncio.sleep(REFRESH_DELAY_SECONDS)
        finally:
            # Discard BEFORE reading counts: a vote that lands during the edit
            # schedules a new refresh instead of being lost.
            _pending_refresh.discard(token)
        await refresh_post_keyboard(bot, db, post)

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _toast(action: str, label: str, previous_label: str | None) -> str:
    if action == "added":
        return f"✅ Your vote: {label}"
    if action == "changed":
        return f"🔁 Vote changed to: {label}"
    return f"↩️ Your vote for “{previous_label or label}” was removed"


async def _maybe_send_personal_card(
    bot: Bot,
    settings: Settings,
    callback: CallbackQuery,
    post: PostRecord,
    chosen_option: str | None,
) -> bool:
    """Experimental Bot API 10.3 card (rich buttons, ephemeral). Returns True if sent."""
    if not settings.vote_ephemeral_card:
        return False
    try:
        from bot.utils.bot_api_103 import rich_callback_button, send_personal_vote_card

        buttons = [
            rich_callback_button(
                text=("✅ " if btn["vote"] == chosen_option else "") + btn["text"],
                callback_data=build_vote_callback(post.vote_token or "", btn["vote"]),
                style="success" if btn["vote"] == chosen_option else "primary",
            )
            for row in post.buttons
            for btn in row
            if is_vote_button(btn)
        ][:8]
        if not buttons:
            return False
        await send_personal_vote_card(
            bot,
            chat_id=post.channel_id,
            user_id=callback.from_user.id,
            callback_query_id=callback.id,
            buttons=buttons,
        )
        return True
    except Exception as exc:  # unsupported chat type / API rejected -> use the toast
        logger.info("Personal ephemeral vote card unavailable, using toast: %s", exc)
        return False


@router.callback_query(F.data.startswith(f"{VOTE_CALLBACK_PREFIX}:"))
async def cb_vote(
    callback: CallbackQuery, bot: Bot, db: Database, settings: Settings
) -> None:
    parsed = parse_vote_callback(callback.data or "")
    if parsed is None:
        await callback.answer("Invalid vote button.", show_alert=True)
        return
    token, option_id = parsed

    if token == PREVIEW_VOTE_TOKEN:
        await callback.answer(
            "👁 Preview only. Votes are counted on the published post.", show_alert=True
        )
        return

    post = await db.get_post_by_vote_token(token)
    label = _find_vote_label(post, option_id) if post else None
    if post is None or label is None:
        await callback.answer("This vote is no longer available.", show_alert=True)
        return

    action, previous = await db.cast_vote(token, callback.from_user.id, option_id)
    previous_label = _find_vote_label(post, previous) if previous else None

    schedule_refresh(bot, db, post)

    chosen = None if action == "removed" else option_id
    shown_card = await _maybe_send_personal_card(bot, settings, callback, post, chosen)
    await callback.answer(
        _toast(action, label, previous_label) if not shown_card else None
    )
