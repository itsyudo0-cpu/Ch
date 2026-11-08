from __future__ import annotations

import html
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import Database, PostRecord
from bot.keyboards import (
    BTN_MY_POSTS,
    button_builder_keyboard,
    cancel_keyboard,
    confirm_delete_post_keyboard,
    my_post_detail_keyboard,
    my_posts_list_keyboard,
)
from bot.states import EditPublishedPostStates
from bot.utils.button_parser import (
    ButtonParseError,
    has_vote_buttons,
    new_vote_token,
    format_buttons_dsl,
    parse_buttons_text,
    remove_button_by_position,
)
from bot.utils.post_render import push_post_buttons
from bot.utils.telegram_helpers import (
    call_with_retry_after,
    format_telegram_error,
)

router = Router(name="my_posts_router")


def _format_post_detail(post: PostRecord) -> str:
    btn_count = sum(len(r) for r in post.buttons)
    dsl = format_buttons_dsl(post.buttons)
    escaped_dsl = html.escape(dsl) if dsl else "No inline buttons"
    flags: list[str] = []
    if post.silent:
        flags.append("Silent")
    if post.protect_content:
        flags.append("Protected")
    if post.pinned:
        flags.append("Pinned")
    flags_str = ", ".join(flags) if flags else "Standard"

    return (
        f"🗂 <b>Published Post #{post.id}</b>\n\n"
        f"• <b>Channel:</b> {html.escape(post.channel_title)}\n"
        f"• <b>Channel Msg ID:</b> <code>{post.channel_message_id}</code>\n"
        f"• <b>Type:</b> <code>{post.content_type}</code> ({flags_str})\n"
        f"• <b>Published At:</b> <code>{post.created_at} UTC</code>\n"
        f"• <b>Snippet:</b> {html.escape(post.text_preview)}\n\n"
        f"<b>URL Buttons ({btn_count}):</b>\n"
        f"<pre>{escaped_dsl}</pre>"
    )


def _format_pub_edit_status(post: PostRecord, rows: list[list[dict[str, str]]]) -> str:
    total = sum(len(r) for r in rows)
    dsl = format_buttons_dsl(rows)
    escaped_dsl = html.escape(dsl) if dsl else "No buttons (all cleared)"
    return (
        f"🔗 <b>Editing Buttons for Post #{post.id}</b>\n"
        f"Channel: <b>{html.escape(post.channel_title)}</b> (Msg <code>{post.channel_message_id}</code>)\n"
        f"Buttons: <b>{total}</b> across <b>{len(rows)}</b> row(s)\n\n"
        f"<pre>{escaped_dsl}</pre>\n\n"
        "Send new button lines to append, remove buttons below, then tap "
        "<b>💾 Save Buttons to Channel Post</b> to apply changes via <code>editMessageReplyMarkup</code>."
    )


@router.message(F.text == BTN_MY_POSTS)
async def msg_my_posts(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    if not message.from_user:
        return
    posts = await db.list_posts(message.from_user.id)
    text = (
        "🗂 <b>My Published Posts</b>\n\nSelect a post below to edit its URL buttons or delete it from the channel:"
        if posts
        else "🗂 <b>My Published Posts</b>\n\nYou have no published posts yet."
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=my_posts_list_keyboard(posts),
    )


@router.callback_query(F.data == "menu:my_posts")
async def cb_my_posts(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    await state.clear()
    posts = await db.list_posts(callback.from_user.id)
    text = (
        "🗂 <b>My Published Posts</b>\n\nSelect a post below to edit its URL buttons or delete it from the channel:"
        if posts
        else "🗂 <b>My Published Posts</b>\n\nYou have no published posts yet."
    )
    if callback.message:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=my_posts_list_keyboard(posts),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("mypost:view:"))
async def cb_view_post_detail(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    await state.clear()
    post_id = int(callback.data.split(":", 2)[2])  # type: ignore[union-attr]
    post = await db.get_post(callback.from_user.id, post_id)
    if not post:
        await callback.answer("Post not found.", show_alert=True)
        return

    if callback.message:
        await callback.message.edit_text(
            _format_post_detail(post),
            parse_mode="HTML",
            reply_markup=my_post_detail_keyboard(post),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("mypost:editbtns:"))
async def cb_start_edit_published_buttons(
    callback: CallbackQuery, state: FSMContext, db: Database
) -> None:
    post_id = int(callback.data.split(":", 2)[2])  # type: ignore[union-attr]
    post = await db.get_post(callback.from_user.id, post_id)
    if not post:
        await callback.answer("Post not found.", show_alert=True)
        return

    await state.set_state(EditPublishedPostStates.managing_buttons)
    await state.update_data(edit_post_id=post.id, edit_buttons=post.buttons)

    if callback.message:
        await callback.message.edit_text(
            _format_pub_edit_status(post, post.buttons),
            parse_mode="HTML",
            reply_markup=button_builder_keyboard(
                post.buttons, is_editing_published=True, post_id=post.id
            ),
        )
    await callback.answer()


@router.callback_query(
    EditPublishedPostStates.managing_buttons, F.data.startswith("pubedit:")
)
async def cb_pub_edit_actions(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db: Database,
) -> None:
    parts = callback.data.split(":")  # type: ignore[union-attr]
    post_id = int(parts[1])
    action = parts[2]

    post = await db.get_post(callback.from_user.id, post_id)
    if not post:
        await callback.answer("Post not found.", show_alert=True)
        return

    data = await state.get_data()
    rows: list[list[dict[str, str]]] = data.get("edit_buttons", post.buttons)

    if action == "add":
        await state.set_state(EditPublishedPostStates.waiting_for_buttons_input)
        if callback.message:
            await callback.message.edit_text(
                f"➕ <b>Add Button Rows to Post #{post.id}</b>\n\n"
                "Send one row per line, separated by <code>|</code>:\n"
                "<code>Text - https://example.com</code>",
                parse_mode="HTML",
                reply_markup=cancel_keyboard(f"mypost:editbtns:{post.id}"),
            )
        await callback.answer()
        return

    if action == "clear":
        rows = []
        await state.update_data(edit_buttons=rows)
        if callback.message:
            await callback.message.edit_text(
                _format_pub_edit_status(post, rows),
                parse_mode="HTML",
                reply_markup=button_builder_keyboard(
                    rows, is_editing_published=True, post_id=post.id
                ),
            )
        await callback.answer("Buttons cleared. Tap Save to apply.")
        return

    if action == "rm":
        r_idx, c_idx = int(parts[3]), int(parts[4])
        try:
            rows = remove_button_by_position(rows, r_idx, c_idx)
        except IndexError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        await state.update_data(edit_buttons=rows)
        if callback.message:
            await callback.message.edit_text(
                _format_pub_edit_status(post, rows),
                parse_mode="HTML",
                reply_markup=button_builder_keyboard(
                    rows, is_editing_published=True, post_id=post.id
                ),
            )
        await callback.answer("Button removed.")
        return

    if action == "save":
        # Keep the existing token (votes survive edits); create one if the first
        # vote button is added to an older post.
        vote_token = post.vote_token or (
            new_vote_token() if has_vote_buttons(rows) else None
        )
        vote_counts = await db.get_vote_counts(vote_token) if vote_token else {}
        try:
            await push_post_buttons(bot, post, rows, vote_token, vote_counts)
        except Exception as exc:
            err_text = format_telegram_error(exc)
            await callback.answer(f"❌ {err_text}"[:200], show_alert=True)
            return

        await db.update_post_buttons(
            callback.from_user.id, post.id, rows, vote_token
        )
        updated_post = await db.get_post(callback.from_user.id, post.id)
        await state.clear()
        if callback.message and updated_post:
            await callback.message.edit_text(
                f"✅ <b>Buttons updated on channel post!</b>\n\n"
                f"{_format_post_detail(updated_post)}",
                parse_mode="HTML",
                reply_markup=my_post_detail_keyboard(updated_post),
            )
        await callback.answer("Channel post buttons updated!")


@router.message(EditPublishedPostStates.managing_buttons, F.text)
@router.message(EditPublishedPostStates.waiting_for_buttons_input, F.text)
async def msg_pub_edit_parse_buttons(
    message: Message, state: FSMContext, db: Database
) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    post_id = int(data["edit_post_id"])
    post = await db.get_post(message.from_user.id, post_id)
    if not post:
        await state.clear()
        await message.answer("Post not found.")
        return

    existing_rows: list[list[dict[str, str]]] = data.get("edit_buttons", post.buttons)
    try:
        updated_rows = parse_buttons_text(
            raw_text=message.text or "",
            existing_rows=existing_rows,
        )
    except ButtonParseError as exc:
        await message.answer(
            f"❌ <b>Invalid button format:</b>\n{html.escape(str(exc))}",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(f"mypost:editbtns:{post.id}"),
        )
        return

    await state.update_data(edit_buttons=updated_rows)
    await state.set_state(EditPublishedPostStates.managing_buttons)
    await message.answer(
        _format_pub_edit_status(post, updated_rows),
        parse_mode="HTML",
        reply_markup=button_builder_keyboard(
            updated_rows, is_editing_published=True, post_id=post.id
        ),
    )


@router.callback_query(F.data.startswith("mypost:delconfirm:"))
async def cb_confirm_delete_post(
    callback: CallbackQuery, db: Database
) -> None:
    post_id = int(callback.data.split(":", 2)[2])  # type: ignore[union-attr]
    post = await db.get_post(callback.from_user.id, post_id)
    if not post:
        await callback.answer("Post not found.", show_alert=True)
        return

    if callback.message:
        await callback.message.edit_text(
            f"⚠️ <b>Delete Post #{post.id} from {html.escape(post.channel_title)}?</b>\n\n"
            f"This will call <code>deleteMessage</code> on message ID "
            f"<code>{post.channel_message_id}</code> in the channel.",
            parse_mode="HTML",
            reply_markup=confirm_delete_post_keyboard(post.id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("mypost:delete:"))
async def cb_execute_delete_post(
    callback: CallbackQuery, bot: Bot, db: Database
) -> None:
    post_id = int(callback.data.split(":", 2)[2])  # type: ignore[union-attr]
    post = await db.get_post(callback.from_user.id, post_id)
    if not post:
        await callback.answer("Post not found.", show_alert=True)
        return

    try:
        await call_with_retry_after(
            bot.delete_message,
            chat_id=post.channel_id,
            message_id=post.channel_message_id,
        )
    except Exception as exc:
        err_msg = format_telegram_error(exc)
        await callback.answer(f"❌ {err_msg}"[:200], show_alert=True)
        return

    await db.mark_post_deleted(callback.from_user.id, post.id)
    posts = await db.list_posts(callback.from_user.id)
    if callback.message:
        await callback.message.edit_text(
            f"🗑 <b>Post #{post.id} deleted from {html.escape(post.channel_title)}.</b>",
            parse_mode="HTML",
            reply_markup=my_posts_list_keyboard(posts),
        )
    await callback.answer("Post deleted from channel.")
