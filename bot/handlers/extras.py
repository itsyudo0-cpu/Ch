from __future__ import annotations

import asyncio
import html
import logging
import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.db import Database
from bot.handlers.posts import _start_new_post_flow
from bot.keyboards import (
    auto_channels_keyboard,
    cancel_keyboard,
    choose_channel_for_post_keyboard,
    main_menu_inline_keyboard,
)
from bot.states import AdminStates
from bot.utils.button_parser import (
    ButtonParseError,
    build_inline_keyboard,
    fill_template,
    parse_template,
    template_setting_key,
    validate_button_url,
)
from bot.utils.extras import (
    get_events,
    list_users,
    log_event,
    set_menu_link,
)

logger = logging.getLogger(__name__)
router = Router(name="extras_router")
DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


# ------------------------------------------------------------- multipost
@router.callback_query(F.data == "menu:multipost")
async def cb_multipost(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    if not callback.message:
        return
    await _start_new_post_flow(callback.from_user.id, state, db, callback.message.edit_text)
    channels = await db.list_channels(callback.from_user.id)
    if channels:
        ids = [c.channel_id for c in channels]
        await state.update_data(channel_ids=ids)
        await callback.message.edit_reply_markup(
            reply_markup=choose_channel_for_post_keyboard(channels, set(ids))
        )
    await callback.answer("All channels selected")


# ------------------------------------------------------------ event log
@router.callback_query(F.data == "menu:events")
async def cb_events(callback: CallbackQuery, db: Database) -> None:
    events = await get_events(db, callback.from_user.id)
    if events:
        lines = [
            f"<code>{time.strftime('%d %b %H:%M', time.gmtime(t))}</code>  {html.escape(x)}"
            for t, x in events
        ]
        body = "\n".join(lines) + "\n\n<i>Times are UTC.</i>"
    else:
        body = "<i>No events yet. Publish a post and it will appear here.</i>"
    if callback.message:
        await callback.message.edit_text(
            f"🧾 <b>Event Log</b>\n{DIVIDER}\n\n{body}",
            parse_mode="HTML",
            reply_markup=main_menu_inline_keyboard(),
        )
    await callback.answer()


# --------------------------------------------------------- auto-complete
async def _enabled_channels(db: Database, user_id: int, channels) -> set[int]:
    enabled: set[int] = set()
    for ch in channels:
        if await db.get_setting(f"auto_ch:{ch.channel_id}") == str(user_id):
            enabled.add(ch.channel_id)
    return enabled


_AUTO_TEXT = (
    f"🤖 <b>Auto-complete</b>\n{DIVIDER}\n\n"
    "Every new post you publish in a channel (from Telegram directly) gets your "
    "buttons added automatically.\n\n"
    "<b>Setup:</b> in <b>📢 My Channels → 🎨</b> save a format with fixed links, e.g.\n"
    "<pre>#g Join - https://t.me/yourchannel | #r Support - https://t.me/you</pre>\n"
    "then switch the channel <b>ON</b> below. The bot needs <i>Edit Messages</i> admin right."
)


@router.callback_query(F.data == "menu:auto")
async def cb_auto_menu(callback: CallbackQuery, db: Database) -> None:
    channels = await db.list_channels(callback.from_user.id)
    if callback.message:
        await callback.message.edit_text(
            _AUTO_TEXT if channels else "⚠️ Connect a channel first (➕ Add Channel).",
            parse_mode="HTML",
            reply_markup=auto_channels_keyboard(
                channels, await _enabled_channels(db, callback.from_user.id, channels)
            ),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("auto:"))
async def cb_auto_toggle(callback: CallbackQuery, db: Database) -> None:
    user_id = callback.from_user.id
    channel_id = int(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    key = f"auto_ch:{channel_id}"
    if await db.get_setting(key) == str(user_id):
        await db.delete_setting(key)
        note = "Auto-complete OFF"
    else:
        raw = await db.get_setting(template_setting_key(user_id, channel_id))
        try:
            rows = fill_template(parse_template(raw or ""), [])
            if not rows:
                raise ButtonParseError("empty")
        except ButtonParseError:
            await callback.answer(
                "Save a format with fixed links first (My Channels → 🎨).",
                show_alert=True,
            )
            return
        await db.set_setting(key, str(user_id))
        note = "Auto-complete ON"
    channels = await db.list_channels(user_id)
    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=auto_channels_keyboard(
                channels, await _enabled_channels(db, user_id, channels)
            )
        )
    await callback.answer(note)


@router.channel_post()
async def on_channel_post(post: Message, bot: Bot, db: Database) -> None:
    if post.reply_markup:
        return
    owner = await db.get_setting(f"auto_ch:{post.chat.id}")
    if not owner:
        return
    raw = await db.get_setting(template_setting_key(int(owner), post.chat.id))
    try:
        rows = fill_template(parse_template(raw or ""), [])
        await bot.edit_message_reply_markup(
            chat_id=post.chat.id,
            message_id=post.message_id,
            reply_markup=build_inline_keyboard(rows),
        )
        await log_event(db, int(owner), f"Auto buttons added in {post.chat.title}")
    except Exception as exc:  # no edit right / bad format: never crash the bot
        logger.warning("Auto-complete failed in %s: %s", post.chat.id, exc)


# ------------------------------------------------- admin: links + broadcast
def _is_admin(settings: Settings, user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.callback_query(F.data.startswith("admin:link:"))
async def cb_admin_link(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    if not _is_admin(settings, callback.from_user.id):
        await callback.answer("⛔ Admins only.", show_alert=True)
        return
    name = callback.data.split(":")[2]  # type: ignore[union-attr]
    await state.set_state(AdminStates.waiting_for_link)
    await state.update_data(link_name=name)
    label = "Guide (Telegraph)" if name == "guide" else "Support"
    if callback.message:
        await callback.message.edit_text(
            f"🔗 <b>Set {label} link</b>\n\nSend the URL now "
            "(<code>https://telegra.ph/...</code> or <code>https://t.me/...</code>).\n"
            "Send <code>remove</code> to delete it.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard("admin:home"),
        )
    await callback.answer()


@router.message(AdminStates.waiting_for_link, F.text)
async def msg_admin_link(
    message: Message, state: FSMContext, db: Database, settings: Settings
) -> None:
    if not message.from_user or not _is_admin(settings, message.from_user.id):
        return
    name = (await state.get_data()).get("link_name", "guide")
    raw = (message.text or "").strip()
    if raw.lower() == "remove":
        await set_menu_link(db, name, None)
        note = "🗑 Link removed."
    else:
        try:
            await set_menu_link(db, name, validate_button_url(raw))
        except ButtonParseError as exc:
            await message.answer(
                f"❌ {html.escape(str(exc))}", reply_markup=cancel_keyboard("admin:home")
            )
            return
        note = "✅ Saved. The menu button now opens it."
    await state.clear()
    await message.answer(note, reply_markup=main_menu_inline_keyboard())


@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast(
    callback: CallbackQuery, state: FSMContext, settings: Settings, db: Database
) -> None:
    if not _is_admin(settings, callback.from_user.id):
        await callback.answer("⛔ Admins only.", show_alert=True)
        return
    users = await list_users(db)
    await state.set_state(AdminStates.waiting_for_broadcast)
    if callback.message:
        await callback.message.edit_text(
            f"📣 <b>Broadcast</b>\n{DIVIDER}\n\n"
            f"Send the message to deliver to <b>{len(users)}</b> bot user(s). "
            "Text, photo, video — anything works, formatting is kept.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard("admin:home"),
        )
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast)
async def msg_admin_broadcast(
    message: Message, state: FSMContext, bot: Bot, db: Database, settings: Settings
) -> None:
    if not message.from_user or not _is_admin(settings, message.from_user.id):
        return
    await state.clear()
    users = await list_users(db)
    status = await message.answer(f"⏳ Sending to {len(users)} user(s)…")
    sent = failed = 0
    for uid in users:
        try:
            await bot.copy_message(uid, message.chat.id, message.message_id)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await log_event(db, message.from_user.id, f"Broadcast: {sent} sent, {failed} failed")
    await status.edit_text(
        f"📣 <b>Broadcast done</b>\n✅ Delivered: <b>{sent}</b>\n❌ Failed: <b>{failed}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_inline_keyboard(),
    )
