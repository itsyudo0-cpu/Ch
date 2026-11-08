from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from bot.db import ChannelRecord, PostRecord

# Main Menu Reply Keyboard labels
BTN_NEW_POST = "📝 New Post"
BTN_MY_CHANNELS = "📢 My Channels"
BTN_MY_POSTS = "🗂 My Posts"
BTN_HELP = "ℹ️ Help"


def main_menu_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NEW_POST), KeyboardButton(text=BTN_MY_CHANNELS)],
            [KeyboardButton(text=BTN_MY_POSTS), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=BTN_NEW_POST, callback_data="menu:new_post"),
                InlineKeyboardButton(text=BTN_MY_CHANNELS, callback_data="menu:channels"),
            ],
            [
                InlineKeyboardButton(text=BTN_MY_POSTS, callback_data="menu:my_posts"),
                InlineKeyboardButton(text=BTN_HELP, callback_data="menu:help"),
            ],
        ]
    )


def channels_list_keyboard(channels: list[ChannelRecord]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        handle = f" (@{ch.username})" if ch.username else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📢 {ch.title}{handle}",
                    callback_data=f"ch_info:{ch.channel_id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Disconnect",
                    callback_data=f"ch_del:{ch.channel_id}",
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="➕ Connect Channel", callback_data="ch_add")]
    )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard(callback_data: str = "action:cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✖️ Cancel", callback_data=callback_data)]
        ]
    )


def choose_channel_for_post_keyboard(
    channels: list[ChannelRecord],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        handle = f" (@{ch.username})" if ch.username else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📢 {ch.title}{handle}",
                    callback_data=f"post_ch:{ch.channel_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="➕ Connect New Channel", callback_data="ch_add")]
    )
    rows.append(
        [InlineKeyboardButton(text="✖️ Cancel", callback_data="action:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def button_builder_keyboard(
    rows: list[list[dict[str, str]]],
    is_editing_published: bool = False,
    post_id: int | None = None,
) -> InlineKeyboardMarkup:
    prefix = f"pubedit:{post_id}" if is_editing_published and post_id else "draftbtn"
    kb_rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="➕ Add Button Rows", callback_data=f"{prefix}:add"
            ),
        ]
    ]

    if rows:
        # Individual button removal buttons
        for r_idx, row in enumerate(rows):
            for c_idx, btn in enumerate(row):
                short_label = btn["text"][:20]
                kb_rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"❌ Remove [{r_idx + 1}.{c_idx + 1}] {short_label}",
                            callback_data=f"{prefix}:rm:{r_idx}:{c_idx}",
                        )
                    ]
                )
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text="🧹 Clear All Buttons", callback_data=f"{prefix}:clear"
                )
            ]
        )

    if is_editing_published and post_id is not None:
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text="💾 Save Buttons to Channel Post",
                    callback_data=f"pubedit:{post_id}:save",
                )
            ]
        )
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text="⬅️ Back to Post", callback_data=f"mypost:view:{post_id}"
                )
            ]
        )
    else:
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text="👁 Preview Post", callback_data="draftbtn:preview"
                ),
                InlineKeyboardButton(
                    text="✖️ Cancel", callback_data="action:cancel"
                ),
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


def preview_controls_keyboard(
    silent: bool,
    protect_content: bool,
    pin_after_publish: bool,
    button_count: int,
    rich_buttons: bool = True,
) -> InlineKeyboardMarkup:
    silent_label = f"{'✅' if silent else '⬜'} Silent Notification"
    protect_label = f"{'✅' if protect_content else '⬜'} Protect Content"
    pin_label = f"{'✅' if pin_after_publish else '⬜'} Pin After Publish"
    btn_label = f"🔗 Edit Buttons ({button_count})"
    rich_label = f"{'🟢' if rich_buttons else '⚪️'} Rich Buttons (API 10.3): {'ON' if rich_buttons else 'OFF'}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Publish Now", callback_data="preview:publish"
                )
            ],
            [
                InlineKeyboardButton(
                    text=btn_label, callback_data="preview:edit_buttons"
                )
            ],
            [
                InlineKeyboardButton(
                    text=silent_label, callback_data="preview:toggle:silent"
                ),
                InlineKeyboardButton(
                    text=protect_label, callback_data="preview:toggle:protect"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=pin_label, callback_data="preview:toggle:pin"
                )
            ],
            [
                InlineKeyboardButton(
                    text=rich_label, callback_data="preview:toggle:rich"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖️ Cancel", callback_data="action:cancel"
                )
            ],
        ]
    )


def my_posts_list_keyboard(posts: list[PostRecord]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for post in posts:
        snippet = post.text_preview[:28] or post.content_type
        btn_count = sum(len(r) for r in post.buttons)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{post.id} [{post.channel_title[:14]}] {snippet} ({btn_count}🔗)",
                    callback_data=f"mypost:view:{post.id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_post_detail_keyboard(post: PostRecord) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if post.channel_username:
        post_url = f"https://t.me/{post.channel_username}/{post.channel_message_id}"
        rows.append(
            [InlineKeyboardButton(text="↗️ Open in Channel", url=post_url)]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔗 Edit URL Buttons",
                callback_data=f"mypost:editbtns:{post.id}",
            ),
            InlineKeyboardButton(
                text="🗑 Delete from Channel",
                callback_data=f"mypost:delconfirm:{post.id}",
            ),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Back to My Posts", callback_data="menu:my_posts")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_post_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ Yes, Delete Post from Channel",
                    callback_data=f"mypost:delete:{post_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Cancel",
                    callback_data=f"mypost:view:{post_id}",
                )
            ],
        ]
    )
