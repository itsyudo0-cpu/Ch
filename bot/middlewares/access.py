from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from bot.config import Settings
from bot.db import Database
from bot.utils.button_parser import VOTE_CALLBACK_PREFIX

logger = logging.getLogger(__name__)


class ContextAndWhitelistMiddleware(BaseMiddleware):
    """
    Injects `db` and `settings` into handler data and enforces optional user whitelist.
    """

    def __init__(self, settings: Settings, db: Database, mongo: Any = None) -> None:
        super().__init__()
        self.settings = settings
        self.db = db
        self.mongo = mongo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["settings"] = self.settings
        data["db"] = self.db
        data["mongo"] = self.mongo

        # Channel subscribers press vote buttons: they are never on the admin whitelist.
        is_vote_press = (
            isinstance(event, CallbackQuery)
            and (event.data or "").startswith(f"{VOTE_CALLBACK_PREFIX}:")
        )

        if self.settings.whitelist_enabled and not is_vote_press:
            user = data.get("event_from_user")
            user_id = user.id if user else None
            if user_id is None or user_id not in self.settings.admin_ids:
                logger.warning(
                    "Blocked unauthorized user_id=%s (whitelist enabled)", user_id
                )
                if isinstance(event, Message):
                    await event.answer(
                        "⛔ Access denied. Your Telegram user ID is not on the bot's whitelist."
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "⛔ Access denied (not whitelisted).", show_alert=True
                    )
                return None

        return await handler(event, data)
