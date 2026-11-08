from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    whitelist_enabled: bool
    db_path: Path
    log_level: str
    vote_ephemeral_card: bool = False
    use_rich_buttons: bool = True


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        if cleaned.lstrip("-").isdigit():
            ids.add(int(cleaned))
    return frozenset(ids)


def load_settings(env_file: str | Path | None = None) -> Settings:
    load_dotenv(dotenv_path=env_file)

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError(
            "BOT_TOKEN is missing. Set BOT_TOKEN in your .env file or environment."
        )

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", "7955232487"))
    whitelist_raw = os.getenv("WHITELIST_ENABLED", "false").strip().lower()
    whitelist_enabled = whitelist_raw in {"1", "true", "yes", "on"}

    db_path = Path(os.getenv("DB_PATH", "channel_help_bot.db").strip())
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    vote_ephemeral_raw = os.getenv("VOTE_EPHEMERAL_CARD", "false").strip().lower()
    vote_ephemeral_card = vote_ephemeral_raw in {"1", "true", "yes", "on"}

    rich_raw = os.getenv("RICH_BUTTONS", "true").strip().lower()
    use_rich_buttons = rich_raw in {"1", "true", "yes", "on"}

    return Settings(
        bot_token=bot_token,
        admin_ids=admin_ids,
        whitelist_enabled=whitelist_enabled,
        db_path=db_path,
        log_level=log_level,
        vote_ephemeral_card=vote_ephemeral_card,
        use_rich_buttons=use_rich_buttons,
    )
