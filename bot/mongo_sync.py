"""
MongoDB multi-URL backup / restore for the bot.

SQLite stays the live database. Every connected MongoDB URL receives a full copy of the
data (channels, posts, votes, settings) every MONGO_SYNC_INTERVAL seconds and once more on
shutdown. When the bot starts with an empty SQLite file (for example after a Render
redeploy) the newest complete copy is restored automatically.

URLs are managed from the admin panel (/admin) and are also stored inside every MongoDB, so
after a redeploy a single URL in the MONGO_URI environment variable is enough to bring all
the other URLs back.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bot.config import Settings
from bot.db import SYNC_TABLES, Database, MongoUrlRecord

logger = logging.getLogger(__name__)

META_COLLECTION = "bot_meta"
META_ID = "meta"
CONFIG_ID = "config"
BATCH_SIZE = 500
NET_TIMEOUT = 15  # seconds for any single MongoDB round trip block

_URI_RE = re.compile(r"^mongodb(\+srv)?://\S+$", re.IGNORECASE)
_CREDS_RE = re.compile(r"(://[^:/@\s]+):[^@\s]+@")


def validate_mongo_uri(uri: str) -> str | None:
    """Return an error message, or None when the URI looks valid."""
    if len(uri) > 2048:
        return "URL is too long."
    if not _URI_RE.match(uri):
        return "URL must start with mongodb:// or mongodb+srv:// and contain no spaces."
    host_part = uri.split("://", 1)[1].split("@")[-1]
    if not host_part or host_part.startswith(("/", "?")):
        return "URL has no host name."
    return None


def mask_uri(uri: str, max_len: int = 64) -> str:
    """Hide the password so a URL can be shown safely in chat."""
    masked = _CREDS_RE.sub(r"\1:••••@", uri)
    masked = masked.split("?", 1)[0]
    return masked if len(masked) <= max_len else masked[: max_len - 1] + "…"


def format_bytes(num: float | int | None) -> str:
    if num is None:
        return "n/a"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def usage_bar(percent: float, width: int = 10) -> str:
    filled = max(0, min(width, round(percent / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def usage_emoji(percent: float) -> str:
    if percent >= 90:
        return "🔴"
    if percent >= 70:
        return "🟡"
    return "🟢"


@dataclass(slots=True)
class DbStatus:
    url: MongoUrlRecord
    online: bool
    latency_ms: float | None = None
    error: str | None = None
    version: str | None = None
    bot_bytes: int | None = None  # storage taken by the bot's own collections
    bot_docs: int | None = None
    bot_collections: int | None = None
    cluster_bytes: int | None = None  # all databases of the cluster (what the quota counts)
    limit_bytes: int = 0
    last_sync: str | None = None
    last_sync_error: str | None = None

    @property
    def used_bytes(self) -> int | None:
        return self.cluster_bytes if self.cluster_bytes is not None else self.bot_bytes

    @property
    def free_bytes(self) -> int | None:
        if self.used_bytes is None:
            return None
        return max(0, self.limit_bytes - self.used_bytes)

    @property
    def percent(self) -> float:
        if self.used_bytes is None or self.limit_bytes <= 0:
            return 0.0
        return min(100.0, self.used_bytes / self.limit_bytes * 100)


@dataclass(slots=True)
class SyncResult:
    url: MongoUrlRecord
    ok: bool
    written: bool = False
    error: str | None = None


def _hash_rows(rows: Any) -> str:
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _doc_id(table: str, row: dict[str, Any]) -> Any:
    keys = SYNC_TABLES[table]
    if len(keys) == 1:
        return row[keys[0]]
    return ":".join(str(row[k]) for k in keys)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class MongoManager:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self._clients: dict[int, Any] = {}
        self._clients_uri: dict[int, str] = {}
        self._last_hash: dict[int, dict[str, str]] = {}
        self._last_sync: dict[int, str] = {}
        self._last_error: dict[int, str | None] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------ clients

    def _client(self, url: MongoUrlRecord) -> Any:
        if self._clients_uri.get(url.id) != url.uri:
            self._clients.pop(url.id, None)
        client = self._clients.get(url.id)
        if client is None:
            try:
                from pymongo import AsyncMongoClient
            except ImportError as exc:  # pragma: no cover - depends on the install
                raise RuntimeError(
                    "pymongo is not installed. Add 'pymongo>=4.13' to requirements.txt."
                ) from exc
            client = AsyncMongoClient(
                url.uri,
                serverSelectionTimeoutMS=8000,
                connectTimeoutMS=8000,
                appname="ChannelHelpBot",
            )
            self._clients[url.id] = client
            self._clients_uri[url.id] = url.uri
        return client

    def _database(self, url: MongoUrlRecord) -> Any:
        return self._client(url)[self.settings.mongo_db_name]

    async def _close_client(self, url_id: int) -> None:
        client = self._clients.pop(url_id, None)
        self._clients_uri.pop(url_id, None)
        self._last_hash.pop(url_id, None)
        self._last_sync.pop(url_id, None)
        self._last_error.pop(url_id, None)
        if client is not None:
            try:
                await client.close()
            except Exception:  # pragma: no cover
                logger.debug("Closing Mongo client failed", exc_info=True)

    # ------------------------------------------------------ add / remove

    async def add_url(
        self, uri: str, limit_mb: int | None = None
    ) -> tuple[MongoUrlRecord | None, str | None]:
        """Validate, test the connection and store a URL. Returns (record, error)."""
        error = validate_mongo_uri(uri)
        if error:
            return None, error

        existing = await self.db.list_mongo_urls()
        if any(u.uri == uri for u in existing):
            return None, "This URL is already added."

        record = await self.db.add_mongo_url(uri, limit_mb=limit_mb, source="panel")
        if record is None:
            return None, "This URL is already added."
        try:
            client = self._client(record)
            await asyncio.wait_for(client.admin.command("ping"), NET_TIMEOUT)
        except Exception as exc:
            await self.db.delete_mongo_url(record.id)
            await self._close_client(record.id)
            return None, f"Could not connect: {_short_error(exc)}"
        return record, None

    async def remove_url(self, url_id: int) -> bool:
        removed = await self.db.delete_mongo_url(url_id)
        await self._close_client(url_id)
        return removed

    # ----------------------------------------------------- startup/restore

    async def bootstrap(self) -> None:
        """Register env URLs and restore the newest snapshot into an empty SQLite file."""
        known = {u.uri for u in await self.db.list_mongo_urls()}
        for uri in self.settings.mongo_uris:
            if uri not in known and validate_mongo_uri(uri) is None:
                await self.db.add_mongo_url(uri, source="env")
        urls = await self.db.list_mongo_urls()
        if not urls:
            return
        if await self.db.is_empty():
            await self._restore_latest(urls)

    async def _restore_latest(self, urls: list[MongoUrlRecord]) -> None:
        candidates: list[tuple[str, MongoUrlRecord]] = []
        for url in urls:
            try:
                meta = await asyncio.wait_for(
                    self._database(url)[META_COLLECTION].find_one({"_id": META_ID}),
                    NET_TIMEOUT,
                )
            except Exception as exc:
                logger.warning("Restore: %s unreachable: %s", mask_uri(url.uri), _short_error(exc))
                continue
            if meta and meta.get("status") == "complete" and meta.get("updated_at"):
                candidates.append((str(meta["updated_at"]), url))
        if not candidates:
            logger.info("Restore: no complete MongoDB snapshot found, starting fresh.")
            return

        candidates.sort(key=lambda item: item[0], reverse=True)
        for updated_at, url in candidates:
            try:
                mdb = self._database(url)
                data: dict[str, list[dict[str, Any]]] = {}
                for table in SYNC_TABLES:
                    rows: list[dict[str, Any]] = []
                    async for doc in mdb[f"data_{table}"].find({}):
                        doc.pop("_id", None)
                        rows.append(doc)
                    data[table] = rows
                config = await mdb[META_COLLECTION].find_one({"_id": CONFIG_ID})
                counts = await self.db.restore_tables(data)
                for item in (config or {}).get("urls", []):
                    uri = str(item.get("uri", ""))
                    if uri and validate_mongo_uri(uri) is None:
                        await self.db.add_mongo_url(
                            uri, limit_mb=item.get("limit_mb"), source="panel"
                        )
                logger.info(
                    "Restored data from %s (snapshot %s UTC): %s",
                    mask_uri(url.uri),
                    updated_at,
                    counts,
                )
                return
            except Exception as exc:
                logger.warning(
                    "Restore from %s failed, trying next: %s",
                    mask_uri(url.uri),
                    _short_error(exc),
                )

    # ------------------------------------------------------------- sync

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="mongo-sync")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        try:  # last copy before the process exits (Render sends SIGTERM on redeploy)
            await asyncio.wait_for(self.sync_now(), 20)
        except Exception as exc:
            logger.warning("Final MongoDB sync failed: %s", _short_error(exc))
        for url_id in list(self._clients):
            await self._close_client(url_id)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.mongo_sync_interval)
            try:
                await self.sync_now()
            except Exception:  # never let the loop die
                logger.exception("MongoDB sync loop error")

    async def sync_now(self, force: bool = False) -> list[SyncResult]:
        async with self._lock:
            urls = await self.db.list_mongo_urls()
            if not urls:
                return []
            dump = await self.db.dump_tables()
            panel_urls = [
                {"uri": u.uri, "limit_mb": u.limit_mb} for u in urls if u.source == "panel"
            ]
            results = await asyncio.gather(
                *(self._sync_one(u, dump, panel_urls, force) for u in urls)
            )
            return list(results)

    async def _sync_one(
        self,
        url: MongoUrlRecord,
        dump: dict[str, list[dict[str, Any]]],
        panel_urls: list[dict[str, Any]],
        force: bool,
    ) -> SyncResult:
        try:
            written = await asyncio.wait_for(
                self._write_snapshot(url, dump, panel_urls, force), 120
            )
            self._last_error[url.id] = None
            if written:
                self._last_sync[url.id] = _now_iso()
            return SyncResult(url=url, ok=True, written=written)
        except Exception as exc:
            msg = _short_error(exc)
            self._last_error[url.id] = msg
            logger.warning("MongoDB sync to %s failed: %s", mask_uri(url.uri), msg)
            return SyncResult(url=url, ok=False, error=msg)

    async def _write_snapshot(
        self,
        url: MongoUrlRecord,
        dump: dict[str, list[dict[str, Any]]],
        panel_urls: list[dict[str, Any]],
        force: bool,
    ) -> bool:
        from pymongo import ReplaceOne

        mdb = self._database(url)
        hashes = self._last_hash.setdefault(url.id, {})
        pending: dict[str, str] = {}

        for table in SYNC_TABLES:
            digest = _hash_rows(dump.get(table, []))
            if force or hashes.get(table) != digest:
                pending[table] = digest
        config_digest = _hash_rows(panel_urls)
        config_changed = force or hashes.get("__config__") != config_digest

        if not pending and not config_changed:
            return False

        meta_col = mdb[META_COLLECTION]
        await meta_col.replace_one(
            {"_id": META_ID}, {"_id": META_ID, "status": "writing"}, upsert=True
        )

        for table in pending:
            rows = dump.get(table, [])
            col = mdb[f"data_{table}"]
            local_ids = set()
            batch: list[Any] = []
            for row in rows:
                doc = dict(row)
                doc["_id"] = _doc_id(table, row)
                local_ids.add(doc["_id"])
                batch.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
                if len(batch) >= BATCH_SIZE:
                    await col.bulk_write(batch, ordered=False)
                    batch = []
            if batch:
                await col.bulk_write(batch, ordered=False)

            if not rows:
                await col.delete_many({})
            elif await col.count_documents({}) > len(local_ids):
                remote_ids = [d["_id"] async for d in col.find({}, {"_id": 1})]
                stale = [i for i in remote_ids if i not in local_ids]
                if stale:
                    await col.delete_many({"_id": {"$in": stale}})

        await meta_col.replace_one(
            {"_id": CONFIG_ID}, {"_id": CONFIG_ID, "urls": panel_urls}, upsert=True
        )
        counts = {t: len(dump.get(t, [])) for t in SYNC_TABLES}
        await meta_col.replace_one(
            {"_id": META_ID},
            {"_id": META_ID, "status": "complete", "updated_at": _now_iso(), "counts": counts},
            upsert=True,
        )
        hashes.update(pending)
        hashes["__config__"] = config_digest
        return True

    # ----------------------------------------------------------- status

    async def status(self) -> list[DbStatus]:
        urls = await self.db.list_mongo_urls()
        return list(await asyncio.gather(*(self._status_one(u) for u in urls)))

    async def _status_one(self, url: MongoUrlRecord) -> DbStatus:
        limit_mb = url.limit_mb or self.settings.mongo_default_limit_mb
        status = DbStatus(
            url=url,
            online=False,
            limit_bytes=limit_mb * 1024 * 1024,
            last_sync=self._last_sync.get(url.id),
            last_sync_error=self._last_error.get(url.id),
        )
        try:
            client = self._client(url)
            started = time.perf_counter()
            await asyncio.wait_for(client.admin.command("ping"), NET_TIMEOUT)
            status.latency_ms = (time.perf_counter() - started) * 1000
            status.online = True
        except Exception as exc:
            status.error = _short_error(exc)
            return status

        try:
            info = await asyncio.wait_for(client.server_info(), NET_TIMEOUT)
            status.version = str(info.get("version", "")) or None
        except Exception:
            pass

        try:
            stats = await asyncio.wait_for(
                client[self.settings.mongo_db_name].command("dbStats"), NET_TIMEOUT
            )
            status.bot_bytes = int(stats.get("storageSize", 0)) + int(stats.get("indexSize", 0))
            status.bot_docs = int(stats.get("objects", 0))
            status.bot_collections = int(stats.get("collections", 0))
        except Exception as exc:
            logger.info("dbStats failed for %s: %s", mask_uri(url.uri), _short_error(exc))

        try:  # whole cluster: this is what an Atlas free-tier quota counts
            listing = await asyncio.wait_for(
                client.admin.command("listDatabases"), NET_TIMEOUT
            )
            total = listing.get("totalSize")
            if total is None:
                total = sum(int(d.get("sizeOnDisk", 0)) for d in listing.get("databases", []))
            status.cluster_bytes = int(total)
        except Exception as exc:
            logger.info("listDatabases failed for %s: %s", mask_uri(url.uri), _short_error(exc))
        return status


def _short_error(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    text = _CREDS_RE.sub(r"\1:••••@", text)
    return text[:160]
