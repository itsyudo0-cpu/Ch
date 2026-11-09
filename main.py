from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from bot.config import load_settings
from bot.db import Database
from bot.handlers import admin, channel_tools, channels, extras, my_posts, posts, start, votes
from bot.utils.extras import load_menu_links
from bot.middlewares.access import ContextAndWhitelistMiddleware
from bot.mongo_sync import MongoManager


def setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


async def start_health_server(logger: logging.Logger) -> web.AppRunner:
    """Tiny HTTP server so Render's Web Service sees an open port.

    Render injects the PORT env var. The bot itself still uses long polling.
    """

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="Bot is running")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("Health server listening on 0.0.0.0:%s", port)
    return runner


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger("channel_help_bot")

    db = Database(settings.db_path)
    await db.init()
    logger.info("SQLite database initialized at %s", settings.db_path)

    # Optional MongoDB backup: restore into an empty SQLite file, then sync in the background.
    mongo = MongoManager(db, settings)
    try:
        await mongo.bootstrap()
    except Exception:
        logger.exception("MongoDB bootstrap failed (continuing without restore)")

    bot = Bot(token=settings.bot_token)
    await load_menu_links(db)
    dp = Dispatcher(storage=MemoryStorage(), db=db)

    middleware = ContextAndWhitelistMiddleware(settings=settings, db=db, mongo=mongo)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    dp.include_router(votes.router)
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(channels.router)
    dp.include_router(posts.router)
    dp.include_router(my_posts.router)
    dp.include_router(extras.router)
    dp.include_router(channel_tools.router)

    bot_info = await bot.get_me()
    logger.info(
        "Starting @%s (id=%s) via long polling | whitelist_enabled=%s",
        bot_info.username,
        bot_info.id,
        settings.whitelist_enabled,
    )

    health_runner = await start_health_server(logger)
    mongo.start()

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await mongo.stop()
        await health_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
