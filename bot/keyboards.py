from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from bot.db import ChannelRecord, MongoUrlRecord, PostRecord
from bot.utils.button_parser import STYLE_EMOJI, api_style, effective_style

# Main Menu Reply Keyboard labels
BTN_NEW_POST = "📝 New Post"
BTN_MY_CHANNELS = "📢 My Channels"
BTN_MY_POSTS = "🗂 My Posts"
BTN_HELP = "ℹ️ Help"

# Telegram colored buttons (Bot API 9.4+): primary = blue, success = green, danger = red.
BLUE = "primary"
GREEN = "success"
RED = "danger"


def _btn(
    text: str,
    *,
    cb: str | None = None,
    url: str | None = None,
    style: str | None = None,
) -> InlineKeyboardButton:
    """InlineKeyboardButton with optional color. Old clients simply ignore `style`."""
    if url is not None:
        return InlineKeyboardButton(text=text, url=url, style=style)
    return InlineKeyboardButton(text=text, callback_data=cb, style=style)


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_NEW_POST, style=GREEN),
                KeyboardButton(text=BTN_MY_CHANNELS, style=BLUE),
            ],
            [
                KeyboardButton(text=BTN_MY_POSTS, style=BLUE),
                KeyboardButton(text=BTN_HELP),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="✨ Choose an option…",
    )


def main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [
            [_btn("✨ Create New Post", cb="menu:new_post", style=GREEN)],
            [
                _btn(BTN_MY_CHANNELS, cb="menu:channels", style=BLUE),
                _btn(BTN_MY_POSTS, cb="menu:my_posts", style=BLUE),
            ],
            [_btn("📖 How it works", cb="menu:help")],
        ]
    )


def channels_list_keyboard(channels: list[ChannelRecord]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        handle = f" (@{ch.username})" if ch.username else ""
        rows.append(
            [
                _btn(f"📢 {ch.title}{handle}", cb=f"ch_info:{ch.channel_id}", style=BLUE),
                _btn("🎨", cb=f"ch_tpl:{ch.channel_id}", style=GREEN),
                _btn("🗑", cb=f"ch_del:{ch.channel_id}", style=RED),
            ]
        )
    rows.append([_btn("➕ Connect Channel", cb="ch_add", style=GREEN)])
    rows.append([_btn("⬅️ Back to Menu", cb="menu:home")])
    return _kb(rows)


def cancel_keyboard(callback_data: str = "action:cancel") -> InlineKeyboardMarkup:
    return _kb([[_btn("✖️ Cancel", cb=callback_data, style=RED)]])


def choose_channel_for_post_keyboard(
    channels: list[ChannelRecord],
    selected: set[int] | None = None,
) -> InlineKeyboardMarkup:
    selected = selected or set()
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        handle = f" (@{ch.username})" if ch.username else ""
        on = ch.channel_id in selected
        rows.append(
            [
                _btn(
                    f"{'✅' if on else '⬜'} {ch.title}{handle}",
                    cb=f"post_ch:{ch.channel_id}",
                    style=GREEN if on else BLUE,
                )
            ]
        )
    if channels:
        rows.append(
            [
                _btn("☑️ Select / Clear All", cb="post_chall", style=BLUE),
                _btn(f"➡️ Continue ({len(selected)})", cb="post_chgo", style=GREEN),
            ]
        )
    rows.append([_btn("➕ Connect New Channel", cb="ch_add", style=GREEN)])
    rows.append([_btn("✖️ Cancel", cb="action:cancel", style=RED)])
    return _kb(rows)


def button_builder_keyboard(
    rows: list[list[dict[str, str]]],
    is_editing_published: bool = False,
    post_id: int | None = None,
) -> InlineKeyboardMarkup:
    prefix = f"pubedit:{post_id}" if is_editing_published and post_id else "draftbtn"
    kb_rows: list[list[InlineKeyboardButton]] = [
        [_btn("➕ Add Button Rows", cb=f"{prefix}:add", style=GREEN)]
    ]

    # One line per button: [🎨 recolor (shows the real color)] [✖ remove]
    for r_idx, row in enumerate(rows):
        for c_idx, btn in enumerate(row):
            short_label = btn["text"][:22]
            kb_rows.append(
                [
                    _btn(
                        f"{STYLE_EMOJI[effective_style(btn)]} {r_idx + 1}.{c_idx + 1} · {short_label}",
                        cb=f"{prefix}:clr:{r_idx}:{c_idx}",
                        style=api_style(btn),
                    ),
                    _btn("✖️", cb=f"{prefix}:rm:{r_idx}:{c_idx}", style=RED),
                ]
            )
    if rows:
        kb_rows.append([_btn("🧹 Clear All Buttons", cb=f"{prefix}:clear")])

    if is_editing_published and post_id is not None:
        kb_rows.append(
            [_btn("💾 Save Buttons to Channel Post", cb=f"pubedit:{post_id}:save", style=GREEN)]
        )
        kb_rows.append([_btn("⬅️ Back to Post", cb=f"mypost:view:{post_id}")])
    else:
        kb_rows.append([_btn("🚀 Publish Now", cb="draftbtn:publish", style=GREEN)])
        kb_rows.append(
            [
                _btn("👁 Preview Post", cb="draftbtn:preview", style=BLUE),
                _btn("✖️ Cancel", cb="action:cancel", style=RED),
            ]
        )

    return _kb(kb_rows)


def preview_controls_keyboard(
    silent: bool,
    protect_content: bool,
    pin_after_publish: bool,
    button_count: int,
    rich_buttons: bool = False,
) -> InlineKeyboardMarkup:
    def toggle(label: str, on: bool, cb: str) -> InlineKeyboardButton:
        return _btn(f"{'✅' if on else '⬜'} {label}", cb=cb, style=GREEN if on else None)

    return _kb(
        [
            [_btn("🚀 Publish Now", cb="preview:publish", style=GREEN)],
            [_btn(f"🎨 Edit Buttons & Colors ({button_count})", cb="preview:edit_buttons", style=BLUE)],
            [
                toggle("Silent", silent, "preview:toggle:silent"),
                toggle("Protect", protect_content, "preview:toggle:protect"),
            ],
            [toggle("Pin After Publish", pin_after_publish, "preview:toggle:pin")],
            [
                toggle(
                    "Compact Rich Buttons (small pills)",
                    rich_buttons,
                    "preview:toggle:rich",
                )
            ],
            [_btn("✖️ Cancel", cb="action:cancel", style=RED)],
        ]
    )


def my_posts_list_keyboard(posts: list[PostRecord]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for post in posts:
        snippet = post.text_preview[:28] or post.content_type
        btn_count = sum(len(r) for r in post.buttons)
        rows.append(
            [
                _btn(
                    f"#{post.id} [{post.channel_title[:14]}] {snippet} ({btn_count}🔗)",
                    cb=f"mypost:view:{post.id}",
                    style=BLUE,
                )
            ]
        )
    rows.append([_btn("⬅️ Back to Menu", cb="menu:home")])
    return _kb(rows)


def my_post_detail_keyboard(post: PostRecord) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if post.channel_username:
        post_url = f"https://t.me/{post.channel_username}/{post.channel_message_id}"
        rows.append([_btn("↗️ Open in Channel", url=post_url, style=BLUE)])
    rows.append(
        [
            _btn("🎨 Edit Buttons", cb=f"mypost:editbtns:{post.id}", style=GREEN),
            _btn("🗑 Delete", cb=f"mypost:delconfirm:{post.id}", style=RED),
        ]
    )
    rows.append([_btn("⬅️ Back to My Posts", cb="menu:my_posts")])
    return _kb(rows)


def confirm_delete_post_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return _kb(
        [
            [_btn("⚠️ Yes, Delete from Channel", cb=f"mypost:delete:{post_id}", style=RED)],
            [_btn("⬅️ Cancel", cb=f"mypost:view:{post_id}", style=GREEN)],
        ]
    )


# ------------------------------------------------------------ admin panel


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [
            [_btn("🗄 Databases", cb="admin:db", style=BLUE)],
            [_btn("📊 DB Status", cb="admin:db:status", style=GREEN)],
            [_btn("🖼 Welcome Image", cb="admin:welcome")],
            [_btn("⬅️ Back to Menu", cb="menu:home")],
        ]
    )


def admin_db_keyboard(urls: list[MongoUrlRecord]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for url in urls:
        tag = "🔒" if url.source == "env" else "🗄"
        rows.append(
            [
                _btn(f"{tag} {url.label}", cb="admin:db:status", style=BLUE),
                _btn("🗑 Delete", cb=f"admin:db:del:{url.id}", style=RED),
            ]
        )
    rows.append([_btn("➕ Add Database URL", cb="admin:db:add", style=GREEN)])
    rows.append(
        [
            _btn("📊 Status", cb="admin:db:status", style=BLUE),
            _btn("🔄 Sync Now", cb="admin:db:sync", style=BLUE),
        ]
    )
    rows.append([_btn("⬅️ Admin Panel", cb="admin:home")])
    return _kb(rows)


def admin_delete_confirm_keyboard(url_id: int) -> InlineKeyboardMarkup:
    return _kb(
        [
            [_btn("⚠️ Yes, Delete URL", cb=f"admin:db:delok:{url_id}", style=RED)],
            [_btn("⬅️ Cancel", cb="admin:db", style=GREEN)],
        ]
    )


def admin_status_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [
            [_btn("🔄 Refresh", cb="admin:db:status", style=BLUE)],
            [_btn("🗄 Databases", cb="admin:db"), _btn("⬅️ Admin Panel", cb="admin:home")],
        ]
    )
