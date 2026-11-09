"""Small persistent helpers stored in bot_settings (synced to MongoDB with the rest)."""

from __future__ import annotations

import json
import time

from bot.db import Database

MAX_EVENTS = 30
MENU_LINKS: dict[str, str] = {}  # "guide" / "support" -> URL (cached for sync keyboards)


async def load_menu_links(db: Database) -> None:
    for name in ("guide", "support"):
        url = await db.get_setting(f"link_{name}")
        if url:
            MENU_LINKS[name] = url
        else:
            MENU_LINKS.pop(name, None)


async def set_menu_link(db: Database, name: str, url: str | None) -> None:
    if url:
        await db.set_setting(f"link_{name}", url)
    else:
        await db.delete_setting(f"link_{name}")
    await load_menu_links(db)


async def _get_json(db: Database, key: str) -> list:
    raw = await db.get_setting(key)
    try:
        data = json.loads(raw) if raw else []
    except ValueError:
        data = []
    return data if isinstance(data, list) else []


async def register_user(db: Database, user_id: int) -> None:
    users = await _get_json(db, "bot_users")
    if user_id not in users:
        users.append(user_id)
        await db.set_setting("bot_users", json.dumps(users))


async def list_users(db: Database) -> list[int]:
    return [int(u) for u in await _get_json(db, "bot_users")]


async def log_event(db: Database, user_id: int, text: str) -> None:
    key = f"events:{user_id}"
    events = await _get_json(db, key)
    events.append([int(time.time()), text])
    await db.set_setting(key, json.dumps(events[-MAX_EVENTS:], ensure_ascii=False))


async def get_events(db: Database, user_id: int, limit: int = 15) -> list[tuple[int, str]]:
    events = await _get_json(db, f"events:{user_id}")
    return [(int(t), str(x)) for t, x in events[-limit:]][::-1]


# ------------------------------------------------ per-channel tool settings
DEFAULT_WELCOME = "👋 <b>Welcome to {channel}, {name}!</b>\nThanks for joining us."
DEFAULT_GOODBYE = "😢 <b>Goodbye, {name}.</b>\nYou left {channel}. You are always welcome back!"


async def get_cfg(db: Database, channel_id: int) -> dict:
    raw = await db.get_setting(f"cfg:{channel_id}")
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


async def save_cfg(db: Database, channel_id: int, cfg: dict) -> None:
    await db.set_setting(f"cfg:{channel_id}", json.dumps(cfg, ensure_ascii=False))
