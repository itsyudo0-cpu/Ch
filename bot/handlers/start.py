from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from aiogram.types import ReplyKeyboardRemove
from bot.config import Settings
from bot.db import Database
from bot.keyboards import (
    BTN_HELP,
    cancel_keyboard,
    main_menu_inline_keyboard,
)
from bot.states import WelcomeStates
from bot.utils.extras import register_user

logger = logging.getLogger(__name__)
router = Router(name="start_router")

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"
WELCOME_IMAGE_KEY = "welcome_image_file_id"
WELCOME_CAPTION_KEY = "welcome_caption_html"
MAX_CAPTION_LEN = 1024

WELCOME_TEXT = (
    "💎 <b>RICH BUTTONS BOT</b> 💎\n"
    f"{DIVIDER}\n"
    "<i>Premium channel posts. Colorful buttons. One tap.</i>\n\n"
    "<blockquote>"
    "🟢 <b>Green</b>  ·  🔵 <b>Blue</b>  ·  🔴 <b>Red</b> buttons\n"
    "📚 Post to many channels at once\n"
    "🤖 Auto-add buttons to every new post\n"
    "🗳 Live vote counters\n"
    "✍️ Edit or delete posts anytime"
    "</blockquote>\n\n"
    "👇 <b>Choose an option to begin</b>"
)

HELP_TEXT = (
    "📖 <b>How to Use Rich Buttons Bot</b>\n"
    f"{DIVIDER}\n\n"
    "1️⃣ <b>Connect a channel</b>\n"
    "Add this bot as <b>Administrator</b> with <i>Post Messages</i> and "
    "<i>Edit Messages</i> rights. Then open <b>📢 My Channels → ➕ Connect Channel</b> "
    "and forward any message from the channel or send its <code>@username</code>.\n\n"
    "2️⃣ <b>Create a post</b>\n"
    "Tap <b>✨ Create New Post</b>, pick the channel and send text, photo, video, "
    "document, GIF, audio or voice with a caption. All formatting is preserved.\n\n"
    "3️⃣ <b>Add colorful buttons</b>\n"
    "One row per line, buttons in the same row separated by <code>|</code>. "
    "A single button fills the whole width, two buttons share it 50/50:\n"
    "<pre>Buy Now - https://example.com\n"
    "Website - https://example.com | Support - tg://resolve?domain=telegram</pre>\n"
    "🎨 <b>Colors</b> — start the button text with a code:\n"
    "<code>#g</code> 🟢 green · <code>#b</code> 🔵 blue (default) · "
    "<code>#r</code> 🔴 red · <code>#n</code> ⚪️ plain\n"
    "<pre>#g Buy Now - https://example.com | #r Cancel - https://example.org</pre>\n"
    "You can also tap any button in the builder to switch its color.\n\n"
    "🗳 <b>Vote buttons</b> — write <code>vote</code> instead of a URL. One vote per "
    "subscriber, live counter on the button:\n"
    "<pre>#g 👍 Like - vote | #r 👎 Dislike - vote</pre>\n"
    "4️⃣ <b>Publish &amp; manage</b>\n"
    "Toggle <i>Silent</i>, <i>Protect</i> or <i>Pin</i> in the preview, then tap "
    "<b>🚀 Publish Now</b>. Later use <b>🗂 My Posts</b> to recolor buttons or delete posts.\n\n"
    "🛡 <b>Admins:</b> /admin opens the admin panel (MongoDB URLs, welcome image) · "
    "/dbstatus shows storage of every database · /setwelcome · /removewelcome."
)


def _is_admin(settings: Settings, user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.admin_ids


async def _send_welcome(message: Message, db: Database) -> None:
    """Welcome card: image (if set by an admin) + caption + persistent main menu."""
    file_id = await db.get_setting(WELCOME_IMAGE_KEY)
    caption = await db.get_setting(WELCOME_CAPTION_KEY) or WELCOME_TEXT
    if file_id:
        try:
            await message.answer_photo(
                photo=file_id,
                caption=caption[:MAX_CAPTION_LEN],
                parse_mode="HTML",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        except Exception as exc:  # stale file_id / bad HTML -> plain welcome
            logger.warning("Welcome image failed, falling back to text: %s", exc)
    await message.answer(
        caption if not file_id else WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    if message.from_user:
        await register_user(db, message.from_user.id)
    await _send_welcome(message, db)
    await message.answer(
        "🧭 <b>Dashboard</b>\n<i>Pick what you want to do:</i>",
        parse_mode="HTML",
        reply_markup=main_menu_inline_keyboard(),
    )


# ------------------------------------------------------------ welcome image


@router.message(Command("setwelcome"))
async def cmd_set_welcome(
    message: Message, state: FSMContext, settings: Settings, db: Database
) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not _is_admin(settings, user_id):
        await message.answer("⛔ Only bot admins can change the welcome image.")
        return

    # Shortcut: /setwelcome as a reply to a photo
    reply = message.reply_to_message
    if reply and reply.photo:
        await _save_welcome(message, db, reply)
        return

    await state.set_state(WelcomeStates.waiting_for_image)
    await message.answer(
        "🖼 <b>Set Welcome Image</b>\n"
        f"{DIVIDER}\n\n"
        "Send me a <b>photo</b> now. It will be shown on <code>/start</code>.\n"
        "💡 The photo's <b>caption</b> becomes the welcome text (formatting kept, "
        "max 1024 chars). No caption = default welcome text.",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


async def _save_welcome(message: Message, db: Database, source: Message) -> None:
    caption = (source.html_text or "") if source.caption else ""
    if len(caption) > MAX_CAPTION_LEN:
        await message.answer(
            f"⚠️ Caption is too long ({len(caption)}/{MAX_CAPTION_LEN}). "
            "Shorten it and send the photo again.",
            reply_markup=cancel_keyboard(),
        )
        return
    await db.set_setting(WELCOME_IMAGE_KEY, source.photo[-1].file_id)  # type: ignore[index]
    if caption:
        await db.set_setting(WELCOME_CAPTION_KEY, caption)
    else:
        await db.delete_setting(WELCOME_CAPTION_KEY)
    await message.answer("✅ <b>Welcome image saved!</b> Preview 👇", parse_mode="HTML")
    await _send_welcome(message, db)


@router.message(WelcomeStates.waiting_for_image, F.photo)
async def msg_receive_welcome_image(
    message: Message, state: FSMContext, db: Database
) -> None:
    await _save_welcome(message, db, message)
    await state.clear()


@router.message(WelcomeStates.waiting_for_image)
async def msg_welcome_not_photo(message: Message) -> None:
    await message.answer(
        "⚠️ Please send a <b>photo</b> (as a picture, not a file).",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )


@router.message(Command("removewelcome"))
async def cmd_remove_welcome(
    message: Message, settings: Settings, db: Database
) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not _is_admin(settings, user_id):
        await message.answer("⛔ Only bot admins can change the welcome image.")
        return
    await db.delete_setting(WELCOME_IMAGE_KEY)
    await db.delete_setting(WELCOME_CAPTION_KEY)
    await message.answer("🗑 Welcome image removed. /start shows the default text again.")


# ------------------------------------------------------------------- menus


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
            "🧭 <b>Dashboard</b>\n<i>Pick what you want to do:</i>",
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
            "✖️ <b>Cancelled.</b> Back to the dashboard:",
            parse_mode="HTML",
            reply_markup=main_menu_inline_keyboard(),
        )
    await callback.answer("Cancelled")
