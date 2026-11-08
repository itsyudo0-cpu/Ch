from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import (
    BTN_HELP,
    BTN_MY_CHANNELS,
    BTN_MY_POSTS,
    BTN_NEW_POST,
    main_menu_inline_keyboard,
    main_menu_reply_keyboard,
)

router = Router(name="start_router")

WELCOME_TEXT = (
    "👋 <b>Welcome to Channel Help Bot!</b>\n\n"
    "Create formatted posts with URL inline buttons, preview them accurately, "
    "and publish or manage them in your Telegram channels.\n\n"
    "Choose an option from the menu below:"
)

HELP_TEXT = (
    "ℹ️ <b>How to Use Channel Help Bot</b>\n\n"
    "1️⃣ <b>Connect a Channel</b>\n"
    "Add this bot to your Telegram channel as an <b>Administrator</b> with "
    "<i>Post Messages</i> and <i>Edit Messages</i> permissions. Then open "
    "<b>📢 My Channels → Connect Channel</b> and forward any message from your "
    "channel or send its <code>@username</code>.\n\n"
    "2️⃣ <b>Create &amp; Preview a Post</b>\n"
    "Tap <b>📝 New Post</b>, select your channel, and send any text, photo, video, "
    "document, GIF, audio, or voice message with caption. All formatting entities "
    "(bold, links, code, quotes, spoilers) are preserved.\n\n"
    "3️⃣ <b>Button Builder Format</b>\n"
    "Send URL buttons one row per line. Separate multiple buttons in the same row "
    "with <code>|</code>:\n"
    "<pre>Read Documentation - https://example.com/docs\n"
    "Website - https://example.com | Telegram - tg://resolve?domain=telegram</pre>\n"
    "Allowed URL schemes: <code>http://</code>, <code>https://</code>, <code>tg://</code>.\n\n"
    "🗳 <b>Vote buttons:</b> write <code>vote</code> instead of a URL. Each subscriber gets "
    "one unique vote per post (tap again to withdraw, tap another option to change), "
    "the counter updates live on the button, and every voter sees their own choice privately:\n"
    "<pre>👍 Like - vote | 👎 Dislike - vote\n"
    "Website - https://example.com</pre>\n\n"
    "🧩 <b>Rich Buttons (Bot API 10.3):</b> posts with buttons are published as Rich Messages, "
    "with the buttons inside the message body instead of the normal inline keyboard. "
    "You can switch this per post in the preview screen.\n\n"
    "4️⃣ <b>Publish &amp; Manage</b>\n"
    "Toggle <i>Silent Notification</i>, <i>Protect Content</i>, or <i>Pin After Publish</i> "
    "in the preview screen, then tap <b>🚀 Publish Now</b>. Later, use <b>🗂 My Posts</b> "
    "to edit URL buttons or delete published posts from the channel."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=main_menu_reply_keyboard(),
    )
    await message.answer(
        "Quick navigation:",
        reply_markup=main_menu_inline_keyboard(),
    )


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        HELP_TEXT,
        parse_mode="HTML",
        reply_markup=main_menu_inline_keyboard(),
    )


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=main_menu_inline_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "menu:help")
async def cb_menu_help(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            HELP_TEXT,
            parse_mode="HTML",
            reply_markup=main_menu_inline_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "action:cancel")
async def cb_cancel_action(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            "✖️ Action cancelled. Returning to main menu:",
            reply_markup=main_menu_inline_keyboard(),
        )
    await callback.answer("Cancelled")
