"""Welcome / Goodbye messages and Join filters for connected channels."""

from __future__ import annotations

import html
import logging
import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.db import Database
from bot.keyboards import BLUE, GREEN, RED, _btn, cancel_keyboard
from bot.states import ToolStates
from bot.utils.extras import (
    DEFAULT_GOODBYE,
    DEFAULT_WELCOME,
    get_cfg,
    log_event,
    save_cfg,
)

logger = logging.getLogger(__name__)
router = Router(name="channel_tools_router")
DIVIDER = "━━━━━━━━━━━━━━━━━━━━"
MAX_TEXT = 1000

# kind -> (title, cfg prefix, default text)
KINDS = {
    "w": ("👋 Welcome message", "welcome", DEFAULT_WELCOME),
    "g": ("🏃 Goodbye message", "goodbye", DEFAULT_GOODBYE),
    "j": ("🛡 Join filters", "jf", ""),
    "f": ("🎨 Button Format", "tpl", ""),
}


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _render(template: str, name: str, channel: str) -> str:
    return template.replace("{name}", html.escape(name)).replace(
        "{channel}", html.escape(channel)
    )


# ------------------------------------------------------------- UI panels
async def _panel(kind: str, channel_id: int, title: str, db: Database):
    cfg = await get_cfg(db, channel_id)
    label, prefix, default = KINDS[kind]
    on = bool(cfg.get(f"{prefix}_on"))
    status = "🟢 <b>ON</b>" if on else "⚪ <b>OFF</b>"
    head = f"{label} — {html.escape(title)}\n{DIVIDER}\n\nStatus: {status}\n\n"
    if kind in ("w", "g"):
        text = cfg.get(f"{prefix}_text") or default
        body = (
            f"<b>Current message:</b>\n<blockquote>{text}</blockquote>\n"
            "Variables: <code>{name}</code> <code>{channel}</code>\n\n"
            "<i>It is sent by DM. Telegram only allows this for users who started "
            "the bot or sent a join request.</i>"
        )
        kb = [
            [_btn("🔴 Turn OFF" if on else "🟢 Turn ON", cb=f"cft:{kind}:{channel_id}:on",
                  style=RED if on else GREEN)],
            [
                _btn("✏️ Set message", cb=f"cfm:{kind}:{channel_id}", style=BLUE),
                _btn("♻️ Reset", cb=f"cfr:{kind}:{channel_id}"),
            ],
            [_btn("⬅️ Back", cb=f"menu:tool:{kind}")],
        ]
    else:
        words = cfg.get("jf_words") or []

        def flag(key: str, label_: str) -> InlineKeyboardButton:
            v = bool(cfg.get(key))
            return _btn(f"{'✅' if v else '⬜'} {label_}", cb=f"cft:j:{channel_id}:{key[3:]}",
                        style=GREEN if v else None)

        body = (
            "When ON, every <b>join request</b> is checked automatically: it is "
            "<b>approved</b> if it passes all the rules below, otherwise <b>declined</b>.\n\n"
            f"🚫 Banned words in name: <b>{len(words)}</b>\n\n"
            "<i>Use a channel invite link with “Request admin approval”. The bot needs "
            "the <b>Invite Users</b> admin right.</i>"
        )
        kb = [
            [_btn("🔴 Turn OFF" if on else "🟢 Turn ON", cb=f"cft:j:{channel_id}:on",
                  style=RED if on else GREEN)],
            [flag("jf_photo", "Require profile photo")],
            [flag("jf_username", "Require username")],
            [_btn("🚫 Banned words", cb=f"cfw:{channel_id}", style=BLUE)],
            [_btn("⬅️ Back", cb="menu:tool:j")],
        ]
    return head + body, _kb(kb)


async def _owned(callback: CallbackQuery, db: Database, channel_id: int):
    ch = await db.get_channel(callback.from_user.id, channel_id)
    if not ch:
        await callback.answer("Channel not found.", show_alert=True)
    return ch


@router.callback_query(F.data.startswith("menu:tool:"))
async def cb_tool_picker(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    kind = callback.data.split(":")[2]  # type: ignore[union-attr]
    channels = await db.list_channels(callback.from_user.id)
    label = KINDS[kind][0]
    if not channels:
        text, rows = "⚠️ Connect a channel first (➕ Add Channel).", []
    else:
        text = f"{label}\n{DIVIDER}\n\nChoose a channel:"
        rows = [
            [
                _btn(
                    f"📢 {c.title}",
                    cb=f"ch_tpl:{c.channel_id}" if kind == "f" else f"cfp:{kind}:{c.channel_id}",
                    style=BLUE,
                )
            ]
            for c in channels
        ]
    rows.append([_btn("⬅️ Back to Menu", cb="menu:home")])
    if callback.message:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_kb(rows))
    await callback.answer()


@router.callback_query(F.data.startswith("cfp:"))
async def cb_tool_panel(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    _, kind, cid = callback.data.split(":")  # type: ignore[union-attr]
    ch = await _owned(callback, db, int(cid))
    if ch and callback.message:
        text, kb = await _panel(kind, ch.channel_id, ch.title, db)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("cft:"))
async def cb_tool_toggle(callback: CallbackQuery, db: Database) -> None:
    _, kind, cid, field = callback.data.split(":")  # type: ignore[union-attr]
    ch = await _owned(callback, db, int(cid))
    if not ch:
        return
    prefix = KINDS[kind][1]
    cfg = await get_cfg(db, ch.channel_id)
    key = f"{prefix}_{field}"
    cfg[key] = not bool(cfg.get(key))
    cfg["owner"] = callback.from_user.id
    await save_cfg(db, ch.channel_id, cfg)
    if callback.message:
        text, kb = await _panel(kind, ch.channel_id, ch.title, db)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer("Saved")


@router.callback_query(F.data.startswith("cfr:"))
async def cb_tool_reset(callback: CallbackQuery, db: Database) -> None:
    _, kind, cid = callback.data.split(":")  # type: ignore[union-attr]
    ch = await _owned(callback, db, int(cid))
    if not ch:
        return
    cfg = await get_cfg(db, ch.channel_id)
    cfg.pop(f"{KINDS[kind][1]}_text", None)
    await save_cfg(db, ch.channel_id, cfg)
    if callback.message:
        text, kb = await _panel(kind, ch.channel_id, ch.title, db)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer("Reset to default")


@router.callback_query(F.data.startswith("cfm:"))
async def cb_tool_set_text(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    _, kind, cid = callback.data.split(":")  # type: ignore[union-attr]
    ch = await _owned(callback, db, int(cid))
    if not ch:
        return
    await state.set_state(ToolStates.waiting_for_text)
    await state.update_data(tool_kind=kind, tool_cid=ch.channel_id)
    if callback.message:
        await callback.message.edit_text(
            f"✏️ <b>{KINDS[kind][0]}</b>\n\nSend the new message (formatting is kept, "
            f"max {MAX_TEXT} characters).\nUse <code>{{name}}</code> for the user's name "
            "and <code>{channel}</code> for the channel title.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(f"cfp:{kind}:{ch.channel_id}"),
        )
    await callback.answer()


@router.message(ToolStates.waiting_for_text, F.text)
async def msg_tool_text(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    kind, cid = data["tool_kind"], int(data["tool_cid"])
    text = message.html_text or ""
    if len(text) > MAX_TEXT:
        await message.answer(f"⚠️ Too long ({len(text)}/{MAX_TEXT}). Send a shorter one.")
        return
    cfg = await get_cfg(db, cid)
    cfg[f"{KINDS[kind][1]}_text"] = text
    cfg["owner"] = message.from_user.id  # type: ignore[union-attr]
    await save_cfg(db, cid, cfg)
    await state.clear()
    ch = await db.get_channel(message.from_user.id, cid)  # type: ignore[union-attr]
    panel_text, kb = await _panel(kind, cid, ch.title if ch else str(cid), db)
    await message.answer("✅ Saved.\n\n" + panel_text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("cfw:"))
async def cb_tool_words(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    ch = await _owned(callback, db, int(callback.data.split(":")[1]))  # type: ignore[union-attr]
    if not ch:
        return
    cfg = await get_cfg(db, ch.channel_id)
    await state.set_state(ToolStates.waiting_for_words)
    await state.update_data(tool_cid=ch.channel_id)
    current = ", ".join(cfg.get("jf_words") or []) or "none"
    if callback.message:
        await callback.message.edit_text(
            "🚫 <b>Banned words</b>\n\nSend words separated by commas. A join request is "
            "declined if the user's name contains any of them.\n"
            f"Current: <code>{html.escape(current)}</code>\n"
            "Send <code>clear</code> to remove all.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(f"cfp:j:{ch.channel_id}"),
        )
    await callback.answer()


@router.message(ToolStates.waiting_for_words, F.text)
async def msg_tool_words(message: Message, state: FSMContext, db: Database) -> None:
    cid = int((await state.get_data())["tool_cid"])
    raw = (message.text or "").strip()
    words = [] if raw.lower() == "clear" else [
        w.strip().lower() for w in raw.replace("\n", ",").split(",") if w.strip()
    ]
    cfg = await get_cfg(db, cid)
    cfg["jf_words"] = words[:50]
    cfg["owner"] = message.from_user.id  # type: ignore[union-attr]
    await save_cfg(db, cid, cfg)
    await state.clear()
    ch = await db.get_channel(message.from_user.id, cid)  # type: ignore[union-attr]
    panel_text, kb = await _panel("j", cid, ch.title if ch else str(cid), db)
    await message.answer("✅ Saved.\n\n" + panel_text, parse_mode="HTML", reply_markup=kb)


# ----------------------------------------------------- live channel events
_recent: dict[tuple[int, int], float] = {}  # (chat, user) -> time of last welcome


async def _dm(bot: Bot, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
        return True
    except Exception:  # user never started the bot / blocked it
        return False


@router.chat_join_request()
async def on_join_request(req: ChatJoinRequest, bot: Bot, db: Database) -> None:
    cfg = await get_cfg(db, req.chat.id)
    if not cfg.get("jf_on"):
        return
    user = req.from_user
    name = f"{user.first_name or ''} {user.last_name or ''} {user.username or ''}".lower()
    ok = True
    if cfg.get("jf_username") and not user.username:
        ok = False
    if ok and any(w and w in name for w in cfg.get("jf_words") or []):
        ok = False
    if ok and cfg.get("jf_photo"):
        try:
            photos = await bot.get_user_profile_photos(user.id, limit=1)
            ok = photos.total_count > 0
        except Exception:
            ok = True  # cannot check -> do not punish the user
    try:
        if ok:
            await bot.approve_chat_join_request(req.chat.id, user.id)
        else:
            await bot.decline_chat_join_request(req.chat.id, user.id)
            if cfg.get("owner"):
                await log_event(db, int(cfg["owner"]), f"Declined join request in {req.chat.title}")
            return
    except Exception as exc:
        logger.warning("Join request handling failed in %s: %s", req.chat.id, exc)
        return
    if cfg.get("welcome_on"):
        text = cfg.get("welcome_text") or DEFAULT_WELCOME
        _recent[(req.chat.id, user.id)] = time.time()
        await _dm(bot, req.user_chat_id, _render(text, user.first_name or "friend", req.chat.title or ""))


@router.chat_member()
async def on_member_update(event: ChatMemberUpdated, bot: Bot, db: Database) -> None:
    new, old = event.new_chat_member, event.old_chat_member
    user = new.user
    if user.is_bot:
        return
    ns, os_ = getattr(new.status, "value", new.status), getattr(old.status, "value", old.status)
    cfg = await get_cfg(db, event.chat.id)
    title = event.chat.title or ""
    name = user.first_name or "friend"
    if ns == "member" and os_ in {"left", "kicked"}:
        if not cfg.get("welcome_on"):
            return
        if time.time() - _recent.pop((event.chat.id, user.id), 0) < 120:
            return  # already welcomed through the join-request flow
        await _dm(bot, user.id, _render(cfg.get("welcome_text") or DEFAULT_WELCOME, name, title))
    elif ns in {"left", "kicked"} and os_ in {"member", "restricted"}:
        if cfg.get("goodbye_on"):
            await _dm(bot, user.id, _render(cfg.get("goodbye_text") or DEFAULT_GOODBYE, name, title))
