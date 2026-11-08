from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_settings
from bot.db import Database
from bot.handlers import channels, my_posts, posts, start, votes
from bot.middlewares.access import ContextAndWhitelistMiddleware


def setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger("channel_help_bot")

    db = Database(settings.db_path)
    await db.init()
    logger.info("SQLite database initialized at %s", settings.db_path)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    middleware = ContextAndWhitelistMiddleware(settings=settings, db=db)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    dp.include_router(votes.router)
    dp.include_router(start.router)
    dp.include_router(channels.router)
    dp.include_router(posts.router)
    dp.include_router(my_posts.router)

    bot_info = await bot.get_me()
    logger.info(
        "Starting @%s (id=%s) via long polling | whitelist_enabled=%s",
        bot_info.username,
        bot_info.id,
        settings.whitelist_enabled,
    )

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
