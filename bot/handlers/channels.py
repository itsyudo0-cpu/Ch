from __future__ import annotations

import html
from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, MessageOriginChannel

from bot.db import Database
from bot.keyboards import (
    BTN_MY_CHANNELS,
    cancel_keyboard,
    channels_list_keyboard,
)
from bot.states import ChannelTemplateStates, ConnectChannelStates
from bot.utils.button_parser import (
    ButtonParseError,
    describe_template,
    parse_template,
    template_setting_key,
)
from bot.keyboards import main_menu_inline_keyboard
from bot.utils.telegram_helpers import verify_channel_and_permissions

router = Router(name="channels_router")


def _render_channels_text(count: int) -> str:
    if count == 0:
        return (
            "📢 <b>My Channels</b>\n\n"
            "You haven't connected any channels yet.\n"
            "Tap <b>➕ Connect Channel</b> below to link your first Telegram channel."
        )
    return (
        f"📢 <b>My Channels</b> ({count} connected)\n\n"
        "Select a channel to verify its status or disconnect it:"
    )


@router.message(F.text == BTN_MY_CHANNELS)
async def msg_my_channels(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    if not message.from_user:
        return
    channels = await db.list_channels(message.from_user.id)
    await message.answer(
        _render_channels_text(len(channels)),
        parse_mode="HTML",
        reply_markup=channels_list_keyboard(channels),
    )


@router.callback_query(F.data == "menu:channels")
async def cb_my_channels(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    await state.clear()
    channels = await db.list_channels(callback.from_user.id)
    if callback.message:
        await callback.message.edit_text(
            _render_channels_text(len(channels)),
            parse_mode="HTML",
            reply_markup=channels_list_keyboard(channels),
        )
    await callback.answer()


@router.callback_query(F.data == "ch_add")
async def cb_connect_channel_start(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    await state.set_state(ConnectChannelStates.waiting_for_channel)
    bot_me = await bot.get_me()
    prompt = (
        "➕ <b>Connect a Telegram Channel</b>\n\n"
        f"1. Add <b>@{bot_me.username}</b> to your channel as an <b>Administrator</b>.\n"
        "2. Grant <b>Post Messages</b> and <b>Edit Messages</b> permissions.\n"
        "3. Now either:\n"
        "   • <b>Forward any message</b> from your channel to this chat, OR\n"
        "   • Send the channel's <code>@username</code> (e.g. <code>@mychannel</code>)."
    )
    if callback.message:
        await callback.message.edit_text(
            prompt,
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
    await callback.answer()


@router.message(ConnectChannelStates.waiting_for_channel)
async def msg_receive_channel_reference(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: Database,
) -> None:
    if not message.from_user:
        return

    target_chat: int | str | None = None

    # Case 1: Forwarded message from a channel (Bot API 7.0+ forward_origin or classic forward_from_chat)
    if isinstance(message.forward_origin, MessageOriginChannel):
        target_chat = message.forward_origin.chat.id
    elif message.forward_from_chat and message.forward_from_chat.type == ChatType.CHANNEL:
        target_chat = message.forward_from_chat.id
    elif message.text:
        cleaned = message.text.strip()
        # Support https://t.me/username or @username
        if cleaned.startswith("https://t.me/") or cleaned.startswith("http://t.me/"):
            slug = cleaned.split("t.me/", 1)[1].strip("/").split("/")[0]
            if slug and not slug.startswith("+"):
                target_chat = f"@{slug.lstrip('@')}"
        elif cleaned.startswith("@") and len(cleaned) > 1:
            target_chat = cleaned
        elif cleaned.startswith("-100") and cleaned[1:].isdigit():
            target_chat = int(cleaned)

    if target_chat is None:
        await message.answer(
            "⚠️ Please <b>forward a message</b> from your channel or send its "
            "public <code>@username</code> (e.g. <code>@my_channel</code>).",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return

    result = await verify_channel_and_permissions(
        bot=bot,
        target_chat_id_or_username=target_chat,
        user_id=message.from_user.id,
    )

    if not result.ok:
        await message.answer(
            f"❌ <b>Could not connect channel:</b>\n{result.error_message}",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return

    record = await db.upsert_channel(
        user_id=message.from_user.id,
        channel_id=result.channel_id,
        title=result.title,
        username=result.username,
    )
    await state.clear()

    channels = await db.list_channels(message.from_user.id)
    handle = f" (@{record.username})" if record.username else ""
    await message.answer(
        f"✅ <b>Channel connected!</b>\n"
        f"Channel: <b>{record.title}</b>{handle}\n"
        f"ID: <code>{record.channel_id}</code>\n\n"
        "Both your admin status and the bot's post/edit permissions are verified.",
        parse_mode="HTML",
        reply_markup=channels_list_keyboard(channels),
    )


@router.callback_query(F.data.startswith("ch_info:"))
async def cb_channel_info(
    callback: CallbackQuery, bot: Bot, db: Database
) -> None:
    channel_id = int(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    ch = await db.get_channel(callback.from_user.id, channel_id)
    if not ch:
        await callback.answer("Channel not found.", show_alert=True)
        return

    verify = await verify_channel_and_permissions(
        bot=bot,
        target_chat_id_or_username=channel_id,
        user_id=callback.from_user.id,
    )
    if verify.ok:
        await db.upsert_channel(
            user_id=callback.from_user.id,
            channel_id=verify.channel_id,
            title=verify.title,
            username=verify.username,
        )
        await callback.answer(
            f"✅ {verify.title}: Bot & Admin permissions OK!", show_alert=True
        )
    else:
        await callback.answer(f"⚠️ {verify.error_message}"[:200], show_alert=True)


@router.callback_query(F.data.startswith("ch_del:"))
async def cb_channel_disconnect(
    callback: CallbackQuery, db: Database
) -> None:
    channel_id = int(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    await db.delete_channel(callback.from_user.id, channel_id)
    channels = await db.list_channels(callback.from_user.id)
    if callback.message:
        await callback.message.edit_text(
            _render_channels_text(len(channels)),
            parse_mode="HTML",
            reply_markup=channels_list_keyboard(channels),
        )
    await callback.answer("Channel disconnected.")


@router.callback_query(F.data.startswith("ch_tpl:"))
async def cb_channel_template(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    channel_id = int(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    ch = await db.get_channel(callback.from_user.id, channel_id)
    if not ch:
        await callback.answer("Channel not found.", show_alert=True)
        return
    current = await db.get_setting(template_setting_key(callback.from_user.id, channel_id))
    await state.set_state(ChannelTemplateStates.waiting_for_template)
    await state.update_data(tpl_channel_id=channel_id)
    if callback.message:
        await callback.message.edit_text(
            f"🎨 <b>Button Format — {html.escape(ch.title)}</b>\n\n"
            "Send your buttons <b>once</b>. Put <code>{link}</code> where the link "
            "changes every time. Fixed links stay as they are.\n\n"
            "<b>Example:</b>\n"
            "<pre>#g Buy Now - {link} | #r Channel - https://t.me/mychannel\n"
            "#b More Info - https://example.com</pre>\n"
            "Colors: <code>#g</code> green · <code>#b</code> blue · <code>#r</code> red · "
            "<code>#n</code> plain. One row per line, <code>|</code> = same row.\n\n"
            "<b>Then, when you create a post:</b> just send the new link — the whole "
            "button set is built automatically.\n"
            "Send <code>clear</code> to remove the format.\n\n"
            + (
                f"<b>Current format:</b>\n<pre>{html.escape(describe_template(parse_template(current)))}</pre>"
                if current
                else "<i>No format saved yet.</i>"
            ),
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
    await callback.answer()


@router.message(ChannelTemplateStates.waiting_for_template, F.text)
async def msg_save_template(
    message: Message, state: FSMContext, db: Database
) -> None:
    data = await state.get_data()
    key = template_setting_key(message.from_user.id, data["tpl_channel_id"])  # type: ignore[union-attr]
    raw = (message.text or "").strip()
    if raw.lower() in {"clear", "off", "remove"}:
        await db.delete_setting(key)
        note = "🗑 Format removed."
    else:
        try:
            parse_template(raw)
        except ButtonParseError as exc:
            await message.answer(
                f"❌ {html.escape(str(exc))}\nSend again:",
                parse_mode="HTML",
                reply_markup=cancel_keyboard(),
            )
            return
        await db.set_setting(key, raw)
        note = (
            "✅ <b>Format saved!</b>\n<pre>"
            + html.escape(describe_template(parse_template(raw)))
            + "</pre>\nWhen you create a post for this channel, just send the link — "
            "the buttons are created automatically."
        )
    await state.clear()
    await message.answer(note, parse_mode="HTML", reply_markup=main_menu_inline_keyboard())
