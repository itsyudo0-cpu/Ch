from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import aiosqlite


@dataclass(slots=True)
class ChannelRecord:
    id: int
    user_id: int
    channel_id: int
    title: str
    username: str | None
    created_at: str


@dataclass(slots=True)
class MongoUrlRecord:
    id: int
    uri: str
    label: str
    limit_mb: int | None
    source: str  # "panel" (added in the admin panel) or "env" (MONGO_URI variable)
    added_at: str


# Tables mirrored to MongoDB: table -> primary key columns.
SYNC_TABLES: dict[str, tuple[str, ...]] = {
    "channels": ("id",),
    "posts": ("id",),
    "votes": ("vote_token", "user_id"),
    "bot_settings": ("key",),
}


@dataclass(slots=True)
class PostRecord:
    id: int
    user_id: int
    channel_id: int
    channel_title: str
    channel_username: str | None
    source_chat_id: int
    source_message_id: int
    channel_message_id: int
    content_type: str
    text_preview: str
    buttons_json: str
    silent: bool
    protect_content: bool
    pinned: bool
    status: str
    created_at: str
    vote_token: str | None = None
    rich_json: str | None = None

    @property
    def rich_content(self) -> dict[str, Any] | None:
        """Stored content of a post published as a Rich Message (None = classic post)."""
        if not self.rich_json:
            return None
        try:
            data = json.loads(self.rich_json)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    @property
    def buttons(self) -> list[list[dict[str, str]]]:
        try:
            data = json.loads(self.buttons_json)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        return []


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    username TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_id, channel_id)
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    channel_title TEXT NOT NULL,
                    channel_username TEXT,
                    source_chat_id INTEGER NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    channel_message_id INTEGER NOT NULL,
                    content_type TEXT NOT NULL,
                    text_preview TEXT NOT NULL DEFAULT '',
                    buttons_json TEXT NOT NULL DEFAULT '[]',
                    silent INTEGER NOT NULL DEFAULT 0,
                    protect_content INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'published',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )
            # Migration: vote support (token links a channel post to its votes)
            cursor = await db.execute("PRAGMA table_info(posts);")
            columns = {row[1] for row in await cursor.fetchall()}
            if "vote_token" not in columns:
                await db.execute("ALTER TABLE posts ADD COLUMN vote_token TEXT;")
            if "rich_json" not in columns:
                await db.execute("ALTER TABLE posts ADD COLUMN rich_json TEXT;")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS votes (
                    vote_token TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    option_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (vote_token, user_id)
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_votes_token_option "
                "ON votes (vote_token, option_id);"
            )
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_vote_token "
                "ON posts (vote_token) WHERE vote_token IS NOT NULL;"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS mongo_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uri TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL DEFAULT '',
                    limit_mb INTEGER,
                    source TEXT NOT NULL DEFAULT 'panel',
                    added_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            await db.commit()

    async def get_setting(self, key: str) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM bot_settings WHERE key = ?;", (key,)
            )
            row = await cursor.fetchone()
            return str(row[0]) if row else None

    async def set_setting(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
                (key, value),
            )
            await db.commit()

    async def delete_setting(self, key: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM bot_settings WHERE key = ?;", (key,))
            await db.commit()

    # ------------------------------------------------------------ MongoDB URLs

    @staticmethod
    def _row_to_mongo_url(row: Any) -> MongoUrlRecord:
        return MongoUrlRecord(
            id=row["id"],
            uri=row["uri"],
            label=row["label"],
            limit_mb=row["limit_mb"],
            source=row["source"],
            added_at=row["added_at"],
        )

    async def list_mongo_urls(self) -> list[MongoUrlRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, uri, label, limit_mb, source, added_at "
                "FROM mongo_urls ORDER BY id ASC;"
            )
            return [self._row_to_mongo_url(r) for r in await cursor.fetchall()]

    async def get_mongo_url(self, url_id: int) -> MongoUrlRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, uri, label, limit_mb, source, added_at "
                "FROM mongo_urls WHERE id = ?;",
                (url_id,),
            )
            row = await cursor.fetchone()
            return self._row_to_mongo_url(row) if row else None

    async def add_mongo_url(
        self,
        uri: str,
        limit_mb: int | None = None,
        source: str = "panel",
    ) -> MongoUrlRecord | None:
        """Insert a URL. Returns None when the same URL already exists."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "INSERT OR IGNORE INTO mongo_urls (uri, limit_mb, source) VALUES (?, ?, ?);",
                (uri, limit_mb, source),
            )
            if cursor.rowcount == 0:
                await db.commit()
                return None
            url_id = int(cursor.lastrowid or 0)
            await db.execute(
                "UPDATE mongo_urls SET label = ? WHERE id = ?;", (f"DB {url_id}", url_id)
            )
            await db.commit()
        return await self.get_mongo_url(url_id)

    async def delete_mongo_url(self, url_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM mongo_urls WHERE id = ?;", (url_id,))
            await db.commit()
            return cursor.rowcount > 0

    # --------------------------------------------- snapshot (MongoDB sync)

    async def is_empty(self) -> bool:
        """True for a brand-new database (nothing worth protecting from a restore)."""
        async with aiosqlite.connect(self.db_path) as db:
            for table in SYNC_TABLES:
                cursor = await db.execute(f"SELECT 1 FROM {table} LIMIT 1;")
                if await cursor.fetchone():
                    return False
        return True

    async def dump_tables(self) -> dict[str, list[dict[str, Any]]]:
        """All synced tables as plain dicts (used to build a MongoDB snapshot)."""
        result: dict[str, list[dict[str, Any]]] = {}
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            for table in SYNC_TABLES:
                cursor = await db.execute(f"SELECT * FROM {table};")
                result[table] = [dict(r) for r in await cursor.fetchall()]
        return result

    async def restore_tables(self, data: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        """Replace the synced tables with a snapshot. Returns restored row counts."""
        counts: dict[str, int] = {}
        async with aiosqlite.connect(self.db_path) as db:
            for table in SYNC_TABLES:
                cursor = await db.execute(f"PRAGMA table_info({table});")
                columns = [row[1] for row in await cursor.fetchall()]
                await db.execute(f"DELETE FROM {table};")
                rows = data.get(table, [])
                for row in rows:
                    cols = [c for c in columns if c in row]
                    if not cols:
                        continue
                    placeholders = ", ".join("?" for _ in cols)
                    await db.execute(
                        f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) "
                        f"VALUES ({placeholders});",
                        tuple(row[c] for c in cols),
                    )
                counts[table] = len(rows)
            await db.commit()
        return counts

    async def upsert_channel(
        self,
        user_id: int,
        channel_id: int,
        title: str,
        username: str | None,
    ) -> ChannelRecord:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO channels (user_id, channel_id, title, username)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, channel_id) DO UPDATE SET
                    title = excluded.title,
                    username = excluded.username;
                """,
                (user_id, channel_id, title, username),
            )
            await db.commit()

            cursor = await db.execute(
                """
                SELECT id, user_id, channel_id, title, username, created_at
                FROM channels
                WHERE user_id = ? AND channel_id = ?;
                """,
                (user_id, channel_id),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("Failed to upsert channel record.")
            return ChannelRecord(
                id=row["id"],
                user_id=row["user_id"],
                channel_id=row["channel_id"],
                title=row["title"],
                username=row["username"],
                created_at=row["created_at"],
            )

    async def list_channels(self, user_id: int) -> list[ChannelRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, user_id, channel_id, title, username, created_at
                FROM channels
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC;
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [
                ChannelRecord(
                    id=row["id"],
                    user_id=row["user_id"],
                    channel_id=row["channel_id"],
                    title=row["title"],
                    username=row["username"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def get_channel(self, user_id: int, channel_id: int) -> ChannelRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, user_id, channel_id, title, username, created_at
                FROM channels
                WHERE user_id = ? AND channel_id = ?;
                """,
                (user_id, channel_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return ChannelRecord(
                id=row["id"],
                user_id=row["user_id"],
                channel_id=row["channel_id"],
                title=row["title"],
                username=row["username"],
                created_at=row["created_at"],
            )

    async def delete_channel(self, user_id: int, channel_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM channels WHERE user_id = ? AND channel_id = ?;",
                (user_id, channel_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def create_post(
        self,
        user_id: int,
        channel_id: int,
        channel_title: str,
        channel_username: str | None,
        source_chat_id: int,
        source_message_id: int,
        channel_message_id: int,
        content_type: str,
        text_preview: str,
        buttons: list[list[dict[str, str]]],
        silent: bool,
        protect_content: bool,
        pinned: bool,
        vote_token: str | None = None,
        rich_content: dict[str, Any] | None = None,
    ) -> int:
        rich_json = (
            json.dumps(rich_content, ensure_ascii=False) if rich_content else None
        )
        buttons_json = json.dumps(buttons, ensure_ascii=False)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO posts (
                    user_id, channel_id, channel_title, channel_username,
                    source_chat_id, source_message_id, channel_message_id,
                    content_type, text_preview, buttons_json,
                    silent, protect_content, pinned, status, vote_token, rich_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?, ?);
                """,
                (
                    user_id,
                    channel_id,
                    channel_title,
                    channel_username,
                    source_chat_id,
                    source_message_id,
                    channel_message_id,
                    content_type,
                    text_preview,
                    buttons_json,
                    int(silent),
                    int(protect_content),
                    int(pinned),
                    vote_token,
                    rich_json,
                ),
            )
            await db.commit()
            return int(cursor.lastrowid or 0)

    async def list_posts(
        self, user_id: int, limit: int = 20, offset: int = 0
    ) -> list[PostRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT *
                FROM posts
                WHERE user_id = ? AND status = 'published'
                ORDER BY id DESC
                LIMIT ? OFFSET ?;
                """,
                (user_id, limit, offset),
            )
            rows = await cursor.fetchall()
            return [self._row_to_post(row) for row in rows]

    async def get_post(self, user_id: int, post_id: int) -> PostRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT *
                FROM posts
                WHERE id = ? AND user_id = ? AND status = 'published';
                """,
                (post_id, user_id),
            )
            row = await cursor.fetchone()
            return self._row_to_post(row) if row is not None else None

    async def update_post_buttons(
        self,
        user_id: int,
        post_id: int,
        buttons: list[list[dict[str, str]]],
        vote_token: str | None = None,
    ) -> bool:
        buttons_json = json.dumps(buttons, ensure_ascii=False)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE posts
                SET buttons_json = ?,
                    vote_token = COALESCE(vote_token, ?)
                WHERE id = ? AND user_id = ? AND status = 'published';
                """,
                (buttons_json, vote_token, post_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def mark_post_deleted(self, user_id: int, post_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE posts
                SET status = 'deleted'
                WHERE id = ? AND user_id = ?;
                """,
                (post_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------ votes

    async def get_post_by_vote_token(self, vote_token: str) -> PostRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM posts WHERE vote_token = ? AND status = 'published';",
                (vote_token,),
            )
            row = await cursor.fetchone()
            return self._row_to_post(row) if row is not None else None

    async def cast_vote(
        self, vote_token: str, user_id: int, option_id: str
    ) -> tuple[str, str | None]:
        """
        One vote per user per post (enforced by the PRIMARY KEY).

        Returns (action, previous_option_id) where action is:
        - "added":   first vote of this user
        - "changed": user moved their vote to another option
        - "removed": user tapped the option they had already chosen (vote withdrawn)
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE;")
            try:
                cursor = await db.execute(
                    "SELECT option_id FROM votes WHERE vote_token = ? AND user_id = ?;",
                    (vote_token, user_id),
                )
                row = await cursor.fetchone()
                previous = row[0] if row else None
                if previous is None:
                    await db.execute(
                        "INSERT INTO votes (vote_token, user_id, option_id) VALUES (?, ?, ?);",
                        (vote_token, user_id, option_id),
                    )
                    action = "added"
                elif previous == option_id:
                    await db.execute(
                        "DELETE FROM votes WHERE vote_token = ? AND user_id = ?;",
                        (vote_token, user_id),
                    )
                    action = "removed"
                else:
                    await db.execute(
                        "UPDATE votes SET option_id = ?, created_at = datetime('now') "
                        "WHERE vote_token = ? AND user_id = ?;",
                        (option_id, vote_token, user_id),
                    )
                    action = "changed"
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            return action, previous

    async def get_vote_counts(self, vote_token: str) -> dict[str, int]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT option_id, COUNT(*) FROM votes WHERE vote_token = ? GROUP BY option_id;",
                (vote_token,),
            )
            return {str(opt): int(cnt) for opt, cnt in await cursor.fetchall()}

    async def get_user_vote(self, vote_token: str, user_id: int) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT option_id FROM votes WHERE vote_token = ? AND user_id = ?;",
                (vote_token, user_id),
            )
            row = await cursor.fetchone()
            return str(row[0]) if row else None

    @staticmethod
    def _row_to_post(row: Any) -> PostRecord:
        return PostRecord(
            id=row["id"],
            user_id=row["user_id"],
            channel_id=row["channel_id"],
            channel_title=row["channel_title"],
            channel_username=row["channel_username"],
            source_chat_id=row["source_chat_id"],
            source_message_id=row["source_message_id"],
            channel_message_id=row["channel_message_id"],
            content_type=row["content_type"],
            text_preview=row["text_preview"],
            buttons_json=row["buttons_json"],
            silent=bool(row["silent"]),
            protect_content=bool(row["protect_content"]),
            pinned=bool(row["pinned"]),
            status=row["status"],
            created_at=row["created_at"],
            vote_token=row["vote_token"],
            rich_json=row["rich_json"],
        )
