from __future__ import annotations

import html
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import Database
from bot.keyboards import (
    BTN_NEW_POST,
    button_builder_keyboard,
    cancel_keyboard,
    choose_channel_for_post_keyboard,
    main_menu_inline_keyboard,
    preview_controls_keyboard,
)
from bot.states import NewPostStates
from bot.config import Settings
from bot.utils.bot_api_103 import send_rich_post
from bot.utils.rich_post import build_rich_content, build_rich_message
from bot.utils.button_parser import (
    ButtonParseError,
    PREVIEW_VOTE_TOKEN,
    build_inline_keyboard,
    has_vote_buttons,
    new_vote_token,
    format_buttons_dsl,
    parse_buttons_text,
    remove_button_by_position,
)
from bot.utils.telegram_helpers import (
    call_with_retry_after,
    extract_post_metadata,
    format_telegram_error,
    verify_channel_and_permissions,
)

router = Router(name="posts_router")


def _format_button_builder_status(
    channel_title: str,
    content_type: str,
    rows: list[list[dict[str, str]]],
) -> str:
    total_btns = sum(len(r) for r in rows)
    dsl_preview = format_buttons_dsl(rows)
    escaped_dsl = html.escape(dsl_preview) if dsl_preview else "None added yet."

    return (
        f"🔗 <b>Button Builder — {html.escape(channel_title)}</b>\n"
        f"Post type: <code>{content_type}</code> · "
        f"Buttons: <b>{total_btns}</b> across <b>{len(rows)}</b> row(s)\n\n"
        f"<b>Current URL Buttons:</b>\n"
        f"<pre>{escaped_dsl}</pre>\n\n"
        "You can send button definitions directly as text (one row per line, "
        "multiple buttons separated by <code>|</code>):\n"
        "<code>Button Text - https://example.com | Second - https://example.org</code>\n"
        "🗳 Vote button: <code>👍 Like - vote | 👎 Dislike - vote</code>"
    )


async def _start_new_post_flow(
    user_id: int,
    state: FSMContext,
    db: Database,
    send_or_edit_func,
) -> None:
    await state.clear()
    channels = await db.list_channels(user_id)
    if not channels:
        await send_or_edit_func(
            "⚠️ <b>No Channels Connected</b>\n\n"
            "Before creating a post, connect at least one Telegram channel where "
            "the bot is an Administrator.",
            parse_mode="HTML",
            reply_markup=choose_channel_for_post_keyboard([]),
        )
        return

    await state.set_state(NewPostStates.choosing_channel)
    await send_or_edit_func(
        "📝 <b>New Post — Step 1 of 3</b>\n\n"
        "Select the channel you want to publish to:",
        parse_mode="HTML",
        reply_markup=choose_channel_for_post_keyboard(channels),
    )


@router.message(F.text == BTN_NEW_POST)
async def msg_new_post(message: Message, state: FSMContext, db: Database) -> None:
    if not message.from_user:
        return
    await _start_new_post_flow(
        user_id=message.from_user.id,
        state=state,
        db=db,
        send_or_edit_func=message.answer,
    )


@router.callback_query(F.data == "menu:new_post")
async def cb_new_post(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    if callback.message:
        await _start_new_post_flow(
            user_id=callback.from_user.id,
            state=state,
            db=db,
            send_or_edit_func=callback.message.edit_text,
        )
    await callback.answer()


@router.callback_query(NewPostStates.choosing_channel, F.data.startswith("post_ch:"))
async def cb_select_channel_for_post(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    channel_id = int(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    channel = await db.get_channel(callback.from_user.id, channel_id)
    if not channel:
        await callback.answer("Channel not found.", show_alert=True)
        return

    await state.update_data(
        channel_id=channel.channel_id,
        channel_title=channel.title,
        channel_username=channel.username,
        buttons=[],
        silent=False,
        protect_content=False,
        pin_after_publish=False,
        rich_buttons=settings.use_rich_buttons,
    )
    await state.set_state(NewPostStates.waiting_for_content)

    if callback.message:
        await callback.message.edit_text(
            f"📝 <b>New Post for {html.escape(channel.title)} — Step 2 of 3</b>\n\n"
            "Send the post content now. Supported formats:\n"
            "• Text message (all formatting entities preserved)\n"
            "• Photo, Video, Document, or GIF (Animation) with caption\n"
            "• Audio or Voice message with caption",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
    await callback.answer()


@router.message(NewPostStates.waiting_for_content)
async def msg_receive_post_content(
    message: Message, state: FSMContext
) -> None:
    meta = extract_post_metadata(message)
    if meta is None:
        await message.answer(
            "⚠️ Unsupported message type. Please send text, photo, video, "
            "document, GIF (animation), audio, or voice message.",
            reply_markup=cancel_keyboard(),
        )
        return

    content_type, text_preview = meta
    await state.update_data(
        source_chat_id=message.chat.id,
        source_message_id=message.message_id,
        content_type=content_type,
        text_preview=text_preview,
        rich_content=build_rich_content(message),
    )
    await state.set_state(NewPostStates.managing_buttons)
    data = await state.get_data()

    await message.answer(
        _format_button_builder_status(
            channel_title=data["channel_title"],
            content_type=content_type,
            rows=data.get("buttons", []),
        ),
        parse_mode="HTML",
        reply_markup=button_builder_keyboard(data.get("buttons", [])),
    )


@router.callback_query(NewPostStates.managing_buttons, F.data == "draftbtn:add")
async def cb_draft_add_buttons_prompt(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.set_state(NewPostStates.waiting_for_buttons_input)
    if callback.message:
        await callback.message.edit_text(
            "➕ <b>Add URL Buttons</b>\n\n"
            "Send one row per line. Separate buttons in the same row with <code>|</code>.\n"
            "Format: <code>Button Text - https://url</code>\n"
            "Vote button (one unique vote per user): <code>Button Text - vote</code>\n\n"
            "Example:\n"
            "<pre>Official Site - https://example.com\n"
            "Docs - https://example.com/docs | Support - tg://resolve?domain=telegram</pre>",
            parse_mode="HTML",
            reply_markup=cancel_keyboard("draftbtn:back"),
        )
    await callback.answer()


@router.callback_query(F.data == "draftbtn:back")
async def cb_draft_back_to_builder(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.set_state(NewPostStates.managing_buttons)
    data = await state.get_data()
    if callback.message:
        await callback.message.edit_text(
            _format_button_builder_status(
                channel_title=data.get("channel_title", "Channel"),
                content_type=data.get("content_type", "text"),
                rows=data.get("buttons", []),
            ),
            parse_mode="HTML",
            reply_markup=button_builder_keyboard(data.get("buttons", [])),
        )
    await callback.answer()


@router.message(NewPostStates.managing_buttons, F.text)
@router.message(NewPostStates.waiting_for_buttons_input, F.text)
async def msg_draft_parse_buttons(
    message: Message, state: FSMContext
) -> None:
    data = await state.get_data()
    existing_rows: list[list[dict[str, str]]] = data.get("buttons", [])

    try:
        updated_rows = parse_buttons_text(
            raw_text=message.text or "",
            existing_rows=existing_rows,
        )
    except ButtonParseError as exc:
        await message.answer(
            f"❌ <b>Invalid button format:</b>\n{html.escape(str(exc))}\n\n"
            "Please fix and send again:",
            parse_mode="HTML",
            reply_markup=cancel_keyboard("draftbtn:back"),
        )
        return

    await state.update_data(buttons=updated_rows)
    await state.set_state(NewPostStates.managing_buttons)
    await message.answer(
        _format_button_builder_status(
            channel_title=data.get("channel_title", "Channel"),
            content_type=data.get("content_type", "text"),
            rows=updated_rows,
        ),
        parse_mode="HTML",
        reply_markup=button_builder_keyboard(updated_rows),
    )


@router.callback_query(NewPostStates.managing_buttons, F.data == "draftbtn:clear")
async def cb_draft_clear_buttons(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.update_data(buttons=[])
    data = await state.get_data()
    if callback.message:
        await callback.message.edit_text(
            _format_button_builder_status(
                channel_title=data.get("channel_title", "Channel"),
                content_type=data.get("content_type", "text"),
                rows=[],
            ),
            parse_mode="HTML",
            reply_markup=button_builder_keyboard([]),
        )
    await callback.answer("All buttons cleared.")


@router.callback_query(
    NewPostStates.managing_buttons, F.data.startswith("draftbtn:rm:")
)
async def cb_draft_remove_single_button(
    callback: CallbackQuery, state: FSMContext
) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    row_idx, col_idx = int(parts[2]), int(parts[3])
    data = await state.get_data()
    rows: list[list[dict[str, str]]] = data.get("buttons", [])

    try:
        updated_rows = remove_button_by_position(rows, row_idx, col_idx)
    except IndexError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.update_data(buttons=updated_rows)
    if callback.message:
        await callback.message.edit_text(
            _format_button_builder_status(
                channel_title=data.get("channel_title", "Channel"),
                content_type=data.get("content_type", "text"),
                rows=updated_rows,
            ),
            parse_mode="HTML",
            reply_markup=button_builder_keyboard(updated_rows),
        )
    await callback.answer("Button removed.")


def _use_rich(data: dict, rows: list[list[dict[str, str]]]) -> bool:
    """Rich Message mode needs the toggle ON, captured content and at least one button."""
    return bool(data.get("rich_buttons", True) and data.get("rich_content") and rows)


async def _send_post_preview(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    rows: list[list[dict[str, str]]] = data.get("buttons", [])
    use_rich = _use_rich(data, rows)

    # 1. Exact channel preview: Rich Message (buttons inside the message body)
    #    or classic copyMessage + InlineKeyboardMarkup.
    if use_rich:
        await call_with_retry_after(
            send_rich_post,
            bot,
            chat_id,
            build_rich_message(data["rich_content"], rows, PREVIEW_VOTE_TOKEN),
        )
    else:
        await call_with_retry_after(
            bot.copy_message,
            chat_id=chat_id,
            from_chat_id=data["source_chat_id"],
            message_id=data["source_message_id"],
            reply_markup=build_inline_keyboard(rows, vote_token=PREVIEW_VOTE_TOKEN),
        )

    # 2. Control panel message below the preview
    total_btns = sum(len(r) for r in rows)
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"👁 <b>Post Preview for {html.escape(data['channel_title'])}</b>\n"
            "The message above is rendered exactly as it will appear in the channel.\n\n"
            "Configure publish options or publish now:"
        ),
        parse_mode="HTML",
        reply_markup=preview_controls_keyboard(
            silent=bool(data.get("silent", False)),
            protect_content=bool(data.get("protect_content", False)),
            pin_after_publish=bool(data.get("pin_after_publish", False)),
            button_count=total_btns,
            rich_buttons=bool(data.get("rich_buttons", True)),
        ),
    )


@router.callback_query(NewPostStates.managing_buttons, F.data == "draftbtn:preview")
async def cb_show_preview(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    await state.set_state(NewPostStates.previewing)
    if callback.message:
        try:
            await _send_post_preview(bot, callback.message.chat.id, state)
        except Exception as exc:
            await callback.message.answer(
                f"❌ <b>Failed to generate preview:</b>\n{html.escape(format_telegram_error(exc))}",
                parse_mode="HTML",
            )
    await callback.answer()


@router.callback_query(NewPostStates.previewing, F.data.startswith("preview:toggle:"))
async def cb_toggle_publish_option(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    option = callback.data.split(":", 2)[2]  # type: ignore[union-attr]
    data = await state.get_data()

    key_map = {
        "silent": "silent",
        "protect": "protect_content",
        "pin": "pin_after_publish",
        "rich": "rich_buttons",
    }
    target_key = key_map.get(option)
    if not target_key:
        await callback.answer()
        return

    new_val = not bool(data.get(target_key, target_key == "rich_buttons"))
    await state.update_data({target_key: new_val})
    updated = await state.get_data()
    rows: list[list[dict[str, str]]] = updated.get("buttons", [])

    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=preview_controls_keyboard(
                silent=bool(updated.get("silent", False)),
                protect_content=bool(updated.get("protect_content", False)),
                pin_after_publish=bool(updated.get("pin_after_publish", False)),
                button_count=sum(len(r) for r in rows),
                rich_buttons=bool(updated.get("rich_buttons", True)),
            )
        )
        if target_key == "rich_buttons":
            # Show a fresh, accurate preview for the newly selected button style.
            try:
                await _send_post_preview(bot, callback.message.chat.id, state)
            except Exception as exc:
                await callback.message.answer(
                    f"❌ <b>Preview failed:</b>\n{html.escape(format_telegram_error(exc))}",
                    parse_mode="HTML",
                )
    await callback.answer("Option updated")


@router.callback_query(NewPostStates.previewing, F.data == "preview:edit_buttons")
async def cb_preview_back_to_edit_buttons(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.set_state(NewPostStates.managing_buttons)
    data = await state.get_data()
    if callback.message:
        await callback.message.edit_text(
            _format_button_builder_status(
                channel_title=data.get("channel_title", "Channel"),
                content_type=data.get("content_type", "text"),
                rows=data.get("buttons", []),
            ),
            parse_mode="HTML",
            reply_markup=button_builder_keyboard(data.get("buttons", [])),
        )
    await callback.answer()


@router.callback_query(NewPostStates.previewing, F.data == "preview:publish")
async def cb_publish_post(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db: Database,
) -> None:
    data = await state.get_data()
    channel_id: int = data["channel_id"]
    rows: list[list[dict[str, str]]] = data.get("buttons", [])
    silent = bool(data.get("silent", False))
    protect_content = bool(data.get("protect_content", False))
    pin_after_publish = bool(data.get("pin_after_publish", False))

    # Re-verify permissions right before publishing
    verify = await verify_channel_and_permissions(
        bot=bot,
        target_chat_id_or_username=channel_id,
        user_id=callback.from_user.id,
    )
    if not verify.ok:
        if callback.message:
            await callback.message.edit_text(
                f"❌ <b>Cannot publish to channel:</b>\n{html.escape(verify.error_message)}",
                parse_mode="HTML",
                reply_markup=main_menu_inline_keyboard(),
            )
        await callback.answer("Permission check failed", show_alert=True)
        return

    vote_token = new_vote_token() if has_vote_buttons(rows) else None
    use_rich = _use_rich(data, rows)

    try:
        if use_rich:
            channel_message_id = await call_with_retry_after(
                send_rich_post,
                bot,
                channel_id,
                build_rich_message(data["rich_content"], rows, vote_token),
                silent=silent,
                protect_content=protect_content,
            )
        else:
            copied = await call_with_retry_after(
                bot.copy_message,
                chat_id=channel_id,
                from_chat_id=data["source_chat_id"],
                message_id=data["source_message_id"],
                disable_notification=silent,
                protect_content=protect_content,
                reply_markup=build_inline_keyboard(rows, vote_token=vote_token),
            )
            channel_message_id = copied.message_id
    except Exception as exc:
        if callback.message:
            await callback.message.edit_text(
                f"❌ <b>Publishing failed:</b>\n{html.escape(format_telegram_error(exc))}"
                + (
                    "\n\n💡 Rich Buttons need Bot API 10.3. Turn <b>Rich Buttons: OFF</b> "
                    "in the preview screen to use normal inline buttons."
                    if use_rich
                    else ""
                ),
                parse_mode="HTML",
                reply_markup=(
                    preview_controls_keyboard(
                        silent=silent,
                        protect_content=protect_content,
                        pin_after_publish=pin_after_publish,
                        button_count=sum(len(r) for r in rows),
                        rich_buttons=True,
                    )
                    if use_rich
                    else main_menu_inline_keyboard()
                ),
            )
        await callback.answer("Publish failed", show_alert=True)
        return

    pin_warning = ""
    if pin_after_publish:
        try:
            await call_with_retry_after(
                bot.pin_chat_message,
                chat_id=channel_id,
                message_id=channel_message_id,
                disable_notification=silent,
            )
        except Exception as exc:
            pin_warning = (
                f"\n\n⚠️ <i>Note: Post was published, but pinning failed: "
                f"{html.escape(format_telegram_error(exc))}</i>"
            )

    post_id = await db.create_post(
        user_id=callback.from_user.id,
        channel_id=channel_id,
        channel_title=verify.title,
        channel_username=verify.username,
        source_chat_id=data["source_chat_id"],
        source_message_id=data["source_message_id"],
        channel_message_id=channel_message_id,
        content_type=data.get("content_type", "text"),
        text_preview=data.get("text_preview", ""),
        buttons=rows,
        silent=silent,
        protect_content=protect_content,
        pinned=pin_after_publish and not pin_warning,
        vote_token=vote_token,
        rich_content=data.get("rich_content") if use_rich else None,
    )

    await state.clear()
    link_line = ""
    if verify.username:
        link_line = f"\n🔗 <a href='https://t.me/{verify.username}/{channel_message_id}'>View Published Post in @{verify.username}</a>"

    if callback.message:
        await callback.message.edit_text(
            f"✅ <b>Post #{post_id} Published Successfully!</b>\n\n"
            f"Channel: <b>{html.escape(verify.title)}</b>\n"
            f"Channel Message ID: <code>{channel_message_id}</code>"
            f"{link_line}{pin_warning}",
            parse_mode="HTML",
            reply_markup=main_menu_inline_keyboard(),
        )
    await callback.answer("Published!")
