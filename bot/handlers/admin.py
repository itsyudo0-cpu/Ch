from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.db import Database
from bot.keyboards import (
    admin_db_keyboard,
    admin_delete_confirm_keyboard,
    admin_panel_keyboard,
    admin_status_keyboard,
    cancel_keyboard,
)
from bot.mongo_sync import (
    DbStatus,
    MongoManager,
    format_bytes,
    mask_uri,
    usage_bar,
    usage_emoji,
)
from bot.states import AdminStates, WelcomeStates

logger = logging.getLogger(__name__)
router = Router(name="admin_router")

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"
TG_LIMIT = 3800  # keep clear of Telegram's 4096 character cap


def _is_admin(settings: Settings, user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.admin_ids


# ------------------------------------------------------------------ texts


def _panel_text() -> str:
    return (
        "🛡 <b>Admin Panel</b>\n"
        f"{DIVIDER}\n\n"
        "🗄 <b>Databases</b> — add or delete MongoDB URLs (automatic backup)\n"
        "📊 <b>DB Status</b> — storage used / free of every database\n"
        "🖼 <b>Welcome Image</b> — change the /start picture"
    )


async def _db_panel_text(db: Database, settings: Settings) -> str:
    urls = await db.list_mongo_urls()
    lines = [
        "🗄 <b>MongoDB Databases</b>",
        DIVIDER,
        "",
    ]
    if not urls:
        lines.append("No database URL added yet.")
        lines.append("Tap <b>➕ Add Database URL</b> to connect your first MongoDB.")
    for url in urls:
        limit = url.limit_mb or settings.mongo_default_limit_mb
        origin = "🔒 env variable" if url.source == "env" else "🛡 admin panel"
        lines.append(
            f"<b>{html.escape(url.label)}</b> · {origin}\n"
            f"<code>{html.escape(mask_uri(url.uri))}</code>\n"
            f"💾 Limit: <b>{limit} MB</b>\n"
        )
    lines.append(
        "ℹ️ Your data is copied to <b>every</b> URL automatically "
        f"(every {settings.mongo_sync_interval}s and on shutdown). If the bot restarts with an "
        "empty database, the newest copy is restored."
    )
    return "\n".join(lines)


def _status_blocks(statuses: list[DbStatus]) -> list[str]:
    if not statuses:
        return [
            "📊 <b>Database Status</b>\n"
            f"{DIVIDER}\n\n"
            "No database URL added yet. Open /admin → 🗄 Databases → ➕ Add Database URL."
        ]

    blocks: list[str] = []
    total_used = 0
    total_limit = 0
    online = 0
    for idx, st in enumerate(statuses, start=1):
        head = f"<b>{idx}. {html.escape(st.url.label)}</b>"
        uri_line = f"🔗 <code>{html.escape(mask_uri(st.url.uri))}</code>"
        if not st.online:
            blocks.append(
                f"{head} 🔴 <b>Offline</b>\n{uri_line}\n"
                f"⚠️ {html.escape(st.error or 'Connection failed')}"
            )
            total_limit += st.limit_bytes
            continue

        online += 1
        total_limit += st.limit_bytes
        lines = [
            f"{head} 🟢 <b>Online</b> · {st.latency_ms:.0f} ms"
            + (f" · v{html.escape(st.version)}" if st.version else ""),
            uri_line,
        ]
        if st.used_bytes is not None:
            total_used += st.used_bytes
            lines.append(
                f"{usage_emoji(st.percent)} <code>{usage_bar(st.percent)}</code> "
                f"<b>{st.percent:.1f}%</b> full"
            )
            lines.append(
                f"💾 Used: <b>{format_bytes(st.used_bytes)}</b> / "
                f"{format_bytes(st.limit_bytes)} · Free: <b>{format_bytes(st.free_bytes)}</b>"
            )
        else:
            lines.append("💾 Storage info is not available for this user/cluster.")
        if st.bot_bytes is not None:
            lines.append(
                f"📦 Bot data: {format_bytes(st.bot_bytes)} · "
                f"{st.bot_docs or 0} docs · {st.bot_collections or 0} collections"
            )
        if st.last_sync_error:
            lines.append(f"⚠️ Last sync failed: {html.escape(st.last_sync_error)}")
        elif st.last_sync:
            lines.append(f"🔄 Last sync: {st.last_sync} UTC")
        else:
            lines.append("🔄 Last sync: not yet (waiting for changes)")
        blocks.append("\n".join(lines))

    free_total = max(0, total_limit - total_used)
    percent = (total_used / total_limit * 100) if total_limit else 0.0
    summary = (
        "📊 <b>Database Status</b>\n"
        f"{DIVIDER}\n"
        f"🗄 Databases: <b>{len(statuses)}</b> ({online} online)\n"
        f"💾 Total used: <b>{format_bytes(total_used)}</b> of {format_bytes(total_limit)} "
        f"({percent:.1f}%)\n"
        f"🆓 Total free: <b>{format_bytes(free_total)}</b>\n"
        "<i>Used space = whole cluster size when MongoDB allows it, "
        "otherwise only this bot's data.</i>"
    )
    return [summary] + blocks


def _chunk(blocks: list[str]) -> list[str]:
    messages: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > TG_LIMIT and current:
            messages.append(current)
            current = block
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


# --------------------------------------------------------------- commands


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    user_id = message.from_user.id if message.from_user else None
    if not _is_admin(settings, user_id):
        await message.answer("⛔ This panel is for bot admins only.")
        return
    await message.answer(
        _panel_text(), parse_mode="HTML", reply_markup=admin_panel_keyboard()
    )


@router.message(Command("dbstatus"))
async def cmd_dbstatus(
    message: Message, settings: Settings, mongo: MongoManager
) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not _is_admin(settings, user_id):
        await message.answer("⛔ This command is for bot admins only.")
        return
    wait = await message.answer("⏳ Checking databases…")
    statuses = await mongo.status()
    texts = _chunk(_status_blocks(statuses))
    await wait.edit_text(texts[0], parse_mode="HTML")
    for text in texts[1:-1]:
        await message.answer(text, parse_mode="HTML")
    if len(texts) > 1:
        await message.answer(
            texts[-1], parse_mode="HTML", reply_markup=admin_status_keyboard()
        )
    else:
        await wait.edit_reply_markup(reply_markup=admin_status_keyboard())


# ------------------------------------------------------------- callbacks


async def _guard(callback: CallbackQuery, settings: Settings) -> bool:
    if _is_admin(settings, callback.from_user.id):
        return True
    await callback.answer("⛔ Admins only.", show_alert=True)
    return False


@router.callback_query(F.data == "admin:home")
async def cb_admin_home(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not await _guard(callback, settings):
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            _panel_text(), parse_mode="HTML", reply_markup=admin_panel_keyboard()
        )
    await callback.answer()


@router.callback_query(F.data == "admin:welcome")
async def cb_admin_welcome(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not await _guard(callback, settings):
        return
    await state.set_state(WelcomeStates.waiting_for_image)
    if callback.message:
        await callback.message.edit_text(
            "🖼 <b>Set Welcome Image</b>\n"
            f"{DIVIDER}\n\n"
            "Send me a <b>photo</b> now. It will be shown on <code>/start</code>.\n"
            "💡 The photo's <b>caption</b> becomes the welcome text (formatting kept, "
            "max 1024 chars). No caption = default welcome text.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard("admin:home"),
        )
    await callback.answer()


@router.callback_query(F.data == "admin:db")
async def cb_admin_db(
    callback: CallbackQuery, state: FSMContext, settings: Settings, db: Database
) -> None:
    if not await _guard(callback, settings):
        return
    await state.clear()
    urls = await db.list_mongo_urls()
    if callback.message:
        await callback.message.edit_text(
            await _db_panel_text(db, settings),
            parse_mode="HTML",
            reply_markup=admin_db_keyboard(urls),
        )
    await callback.answer()


@router.callback_query(F.data == "admin:db:add")
async def cb_admin_db_add(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not await _guard(callback, settings):
        return
    await state.set_state(AdminStates.waiting_for_mongo_url)
    if callback.message:
        await callback.message.edit_text(
            "➕ <b>Add Database URL</b>\n"
            f"{DIVIDER}\n\n"
            "Send your MongoDB connection string:\n"
            "<code>mongodb+srv://user:password@cluster0.xxxxx.mongodb.net</code>\n\n"
            f"📏 Optional storage limit in MB after a space "
            f"(default <b>{settings.mongo_default_limit_mb} MB</b>, the Atlas free size):\n"
            "<code>mongodb+srv://user:password@cluster0.xxxxx.mongodb.net 1024</code>\n\n"
            "🔐 I will delete your message right after reading it and test the connection.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard("admin:db"),
        )
    await callback.answer()


@router.message(AdminStates.waiting_for_mongo_url, F.text)
async def msg_receive_mongo_url(
    message: Message,
    state: FSMContext,
    settings: Settings,
    db: Database,
    mongo: MongoManager,
) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not _is_admin(settings, user_id):
        return

    parts = (message.text or "").split()
    try:  # the URL contains a password: remove it from the chat
        await message.delete()
    except Exception:
        pass

    if not parts:
        await message.answer("⚠️ Please send the MongoDB URL.", reply_markup=cancel_keyboard("admin:db"))
        return

    limit_mb: int | None = None
    if len(parts) > 1:
        if parts[1].isdigit() and int(parts[1]) > 0:
            limit_mb = int(parts[1])
        else:
            await message.answer(
                "⚠️ The limit must be a number of MB, e.g. <code>512</code>.",
                parse_mode="HTML",
                reply_markup=cancel_keyboard("admin:db"),
            )
            return

    progress = await message.answer("⏳ Testing connection…")
    record, error = await mongo.add_url(parts[0], limit_mb=limit_mb)
    if record is None:
        await progress.edit_text(
            f"❌ <b>Could not add URL</b>\n{html.escape(error or 'Unknown error')}\n\n"
            "Fix it and send the URL again:",
            parse_mode="HTML",
            reply_markup=cancel_keyboard("admin:db"),
        )
        return

    await state.clear()
    await progress.edit_text("✅ Connected! Copying your data to the new database…")
    results = await mongo.sync_now()
    mine = next((r for r in results if r.url.id == record.id), None)
    note = (
        "✅ Data copied."
        if mine and mine.ok
        else f"⚠️ Connected, but the first copy failed: {html.escape(mine.error or '')}"
        if mine
        else ""
    )
    urls = await db.list_mongo_urls()
    await progress.edit_text(
        f"✅ <b>{html.escape(record.label)} added</b>\n"
        f"<code>{html.escape(mask_uri(record.uri))}</code>\n{note}\n\n"
        + await _db_panel_text(db, settings),
        parse_mode="HTML",
        reply_markup=admin_db_keyboard(urls),
    )


@router.message(AdminStates.waiting_for_mongo_url)
async def msg_mongo_url_not_text(message: Message) -> None:
    await message.answer(
        "⚠️ Please send the MongoDB URL as text.", reply_markup=cancel_keyboard("admin:db")
    )


@router.callback_query(F.data.startswith("admin:db:del:"))
async def cb_admin_db_delete(
    callback: CallbackQuery, settings: Settings, db: Database
) -> None:
    if not await _guard(callback, settings):
        return
    url_id = int((callback.data or "").rsplit(":", 1)[1])
    url = await db.get_mongo_url(url_id)
    if url is None:
        await callback.answer("URL not found.", show_alert=True)
        return
    if url.source == "env":
        await callback.answer(
            "This URL comes from the MONGO_URI environment variable. "
            "Remove it there (Render → Environment) to delete it.",
            show_alert=True,
        )
        return
    if callback.message:
        await callback.message.edit_text(
            f"⚠️ <b>Delete {html.escape(url.label)}?</b>\n"
            f"<code>{html.escape(mask_uri(url.uri))}</code>\n\n"
            "The bot stops using this database. Data already stored inside it is "
            "<b>not</b> erased.",
            parse_mode="HTML",
            reply_markup=admin_delete_confirm_keyboard(url.id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:db:delok:"))
async def cb_admin_db_delete_ok(
    callback: CallbackQuery, settings: Settings, db: Database, mongo: MongoManager
) -> None:
    if not await _guard(callback, settings):
        return
    url_id = int((callback.data or "").rsplit(":", 1)[1])
    url = await db.get_mongo_url(url_id)
    if url is None or url.source == "env":
        await callback.answer("Cannot delete this URL.", show_alert=True)
        return
    await mongo.remove_url(url_id)
    urls = await db.list_mongo_urls()
    if callback.message:
        await callback.message.edit_text(
            await _db_panel_text(db, settings),
            parse_mode="HTML",
            reply_markup=admin_db_keyboard(urls),
        )
    await callback.answer(f"🗑 {url.label} deleted")


@router.callback_query(F.data == "admin:db:sync")
async def cb_admin_db_sync(
    callback: CallbackQuery, settings: Settings, mongo: MongoManager
) -> None:
    if not await _guard(callback, settings):
        return
    await callback.answer("⏳ Syncing…")
    results = await mongo.sync_now(force=True)
    if not results:
        text = "No database URL added yet."
    else:
        ok = sum(1 for r in results if r.ok)
        text = f"🔄 Synced {ok}/{len(results)} database(s)."
        failed = [r for r in results if not r.ok]
        if failed:
            text += "\n⚠️ " + "; ".join(f"{r.url.label}: {r.error}" for r in failed)
    if callback.message:
        await callback.message.answer(text[:600])


@router.callback_query(F.data == "admin:db:status")
async def cb_admin_db_status(
    callback: CallbackQuery, settings: Settings, mongo: MongoManager
) -> None:
    if not await _guard(callback, settings):
        return
    await callback.answer("⏳ Checking…")
    if not callback.message:
        return
    statuses = await mongo.status()
    texts = _chunk(_status_blocks(statuses))
    try:
        await callback.message.edit_text(
            texts[0],
            parse_mode="HTML",
            reply_markup=admin_status_keyboard() if len(texts) == 1 else None,
        )
    except Exception:  # "message is not modified" when nothing changed
        pass
    for i, text in enumerate(texts[1:], start=1):
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=admin_status_keyboard() if i == len(texts) - 1 else None,
        )
