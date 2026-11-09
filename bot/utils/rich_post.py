"""
Build Bot API 10.3 Rich Messages for channel posts.

Instead of `copyMessage + InlineKeyboardMarkup`, a post with buttons is sent with
`sendRichMessage` as blocks: [media block] + [paragraph block] + [buttons blocks].
The buttons are `RichMessageButton`s inside the message body (not an inline keyboard).

Everything here is pure data conversion (no network), so it is unit-tested.
"""

from __future__ import annotations

import os
import unicodedata
from typing import Any

from bot.utils.button_parser import (
    api_style,
    build_vote_callback,
    is_vote_button,
    _vote_label,
)

RICH_BUTTON_ALIGN = "center"
# Rich buttons cannot be stretched by the API (only left/center/right), so labels are
# padded with invisible Braille-blank characters to make the pills wide.
# RICH_ROW_WIDTH = total label width of one row (0 = no padding). Raise it for wider pills.
try:
    RICH_ROW_WIDTH = int(os.getenv("RICH_ROW_WIDTH", "34"))
except ValueError:
    RICH_ROW_WIDTH = 34
_PAD_CHAR = "\u2800"
MAX_RICH_BUTTON_TEXT = 64
MAX_RICH_TEXT_CHARS = 32768

# content_type -> (block type, field name, InputMedia type)
_MEDIA_BLOCKS: dict[str, tuple[str, str, str]] = {
    "photo": ("photo", "photo", "photo"),
    "video": ("video", "video", "video"),
    "animation": ("animation", "animation", "animation"),
    "audio": ("audio", "audio", "audio"),
    "voice": ("voice_note", "voice_note", "voice_note"),
    "document": ("document", "document", "document"),
}


# ---------------------------------------------------------------- capture


def serialize_entities(entities: list[Any] | None) -> list[dict[str, Any]]:
    """aiogram MessageEntity list -> plain JSON-safe dicts (stored in FSM / DB)."""
    result: list[dict[str, Any]] = []
    for ent in entities or []:
        item: dict[str, Any] = {
            "type": ent.type,
            "offset": ent.offset,
            "length": ent.length,
        }
        if getattr(ent, "url", None):
            item["url"] = ent.url
        if getattr(ent, "custom_emoji_id", None):
            item["custom_emoji_id"] = ent.custom_emoji_id
        user = getattr(ent, "user", None)
        if user is not None:
            item["user"] = {
                "id": user.id,
                "is_bot": bool(user.is_bot),
                "first_name": user.first_name,
            }
        result.append(item)
    return result


def build_rich_content(message: Any) -> dict[str, Any]:
    """Extract everything needed to re-create a user's message as a rich message."""
    text = message.text or message.caption or ""
    entities = message.entities if message.text else message.caption_entities
    content_type, file_id = "text", None
    if message.photo:
        content_type, file_id = "photo", message.photo[-1].file_id
    elif message.video:
        content_type, file_id = "video", message.video.file_id
    elif message.animation:
        content_type, file_id = "animation", message.animation.file_id
    elif message.document:
        content_type, file_id = "document", message.document.file_id
    elif message.audio:
        content_type, file_id = "audio", message.audio.file_id
    elif message.voice:
        content_type, file_id = "voice", message.voice.file_id
    return {
        "content_type": content_type,
        "file_id": file_id,
        "text": text,
        "entities": serialize_entities(entities),
    }


# ------------------------------------------------- entities -> RichText


def _decode(data: bytes, start: int, end: int) -> str:
    return data[start * 2 : end * 2].decode("utf-16-le", errors="ignore")


def _compact(parts: list[Any]) -> Any:
    merged: list[Any] = []
    for part in parts:
        if part == "":
            continue
        if isinstance(part, str) and merged and isinstance(merged[-1], str):
            merged[-1] += part
        else:
            merged.append(part)
    if not merged:
        return ""
    return merged[0] if len(merged) == 1 else merged


_SIMPLE_WRAP = {
    "bold": "bold",
    "italic": "italic",
    "underline": "underline",
    "strikethrough": "strikethrough",
    "spoiler": "spoiler",
    "code": "code",
    "pre": "code",
}


def _wrap(ent: dict[str, Any], inner: Any, plain: str) -> Any:
    etype = ent.get("type")
    if etype in _SIMPLE_WRAP:
        return {"type": _SIMPLE_WRAP[etype], "text": inner}
    if etype == "text_link" and ent.get("url"):
        return {"type": "url", "text": inner, "url": ent["url"]}
    if etype == "text_mention" and ent.get("user"):
        return {"type": "text_mention", "text": inner, "user": ent["user"]}
    if etype == "custom_emoji" and ent.get("custom_emoji_id"):
        return {
            "type": "custom_emoji",
            "custom_emoji_id": ent["custom_emoji_id"],
            "alternative_text": plain or "🙂",
        }
    # url / mention / hashtag / blockquote / ...: plain text (auto-detection handles links)
    return inner


def _render(data: bytes, start: int, end: int, ents: list[dict[str, Any]]) -> Any:
    parts: list[Any] = []
    pos = start
    i = 0
    while i < len(ents):
        ent = ents[i]
        e_start = int(ent["offset"])
        e_end = e_start + int(ent["length"])
        if e_start < pos or e_end > end or e_end <= e_start:
            i += 1  # overlapping / out of range entity: ignore
            continue
        if e_start > pos:
            parts.append(_decode(data, pos, e_start))
        j = i + 1
        children: list[dict[str, Any]] = []
        while j < len(ents) and int(ents[j]["offset"]) < e_end:
            if int(ents[j]["offset"]) + int(ents[j]["length"]) <= e_end:
                children.append(ents[j])
            j += 1
        inner = _render(data, e_start, e_end, children)
        parts.append(_wrap(ent, inner, _decode(data, e_start, e_end)))
        pos = e_end
        i = j
    if pos < end:
        parts.append(_decode(data, pos, end))
    return _compact(parts)


def entities_to_rich_text(text: str, entities: list[dict[str, Any]] | None) -> Any:
    """Telegram text + entities (UTF-16 offsets) -> RichText (string / nested objects)."""
    data = text.encode("utf-16-le")
    total = len(data) // 2
    ordered = sorted(entities or [], key=lambda e: (int(e["offset"]), -int(e["length"])))
    return _render(data, 0, total, ordered)


# ----------------------------------------------------------- blocks


def rich_button_for(
    btn: dict[str, str],
    vote_token: str | None,
    vote_counts: dict[str, int] | None,
) -> dict[str, Any] | None:
    """One stored button dict -> RichMessageButton (exactly one action)."""
    if not btn.get("text"):
        return None
    if is_vote_button(btn):
        if not vote_token:
            return None
        count = (vote_counts or {}).get(btn["vote"], 0)
        out: dict[str, Any] = {
            "text": _vote_label(btn["text"], count),
            "callback_data": build_vote_callback(vote_token, btn["vote"]),
        }
    elif btn.get("url"):
        out = {"text": btn["text"], "url": btn["url"]}
    else:
        return None
    style = api_style(btn)
    if style:
        out["style"] = style
    return out


def _visual_len(text: str) -> int:
    total = 0
    for ch in text:
        wide = unicodedata.east_asian_width(ch) in {"W", "F"} or ord(ch) >= 0x1F000
        total += 2 if wide else 1
    return total


def pad_button_text(text: str, target: int) -> str:
    """Center `text` in invisible padding so the button looks wide."""
    missing = target - _visual_len(text)
    if target <= 0 or missing <= 1:
        return text
    left = missing // 2
    right = missing - left
    left = min(left, max(0, (MAX_RICH_BUTTON_TEXT - len(text)) // 2))
    right = min(right, max(0, MAX_RICH_BUTTON_TEXT - len(text) - left))
    return f"{_PAD_CHAR * left}{text}{_PAD_CHAR * right}"


def build_rich_blocks(
    content: dict[str, Any],
    rows: list[list[dict[str, str]]],
    vote_token: str | None = None,
    vote_counts: dict[str, int] | None = None,
    row_width: int = 0,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    content_type = content.get("content_type", "text")
    file_id = content.get("file_id")
    media = _MEDIA_BLOCKS.get(content_type)
    if media and file_id:
        block_type, field, media_type = media
        blocks.append({"type": block_type, field: {"type": media_type, "media": file_id}})

    text = (content.get("text") or "")[:MAX_RICH_TEXT_CHARS]
    if text.strip():
        blocks.append(
            {
                "type": "paragraph",
                "text": entities_to_rich_text(text, content.get("entities")),
            }
        )

    for row in rows:
        buttons = [
            b
            for b in (rich_button_for(btn, vote_token, vote_counts) for btn in row)
            if b is not None
        ]
        if buttons and row_width > 0:
            per_button = row_width // len(buttons)
            for b in buttons:
                b["text"] = pad_button_text(b["text"], per_button)
        if buttons:
            blocks.append(
                {"type": "buttons", "buttons": buttons[:8], "align": RICH_BUTTON_ALIGN}
            )
    return blocks


def build_rich_message(
    content: dict[str, Any],
    rows: list[list[dict[str, str]]],
    vote_token: str | None = None,
    vote_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """InputRichMessage (blocks mode) for a channel post."""
    return {
        "blocks": build_rich_blocks(
            content, rows, vote_token, vote_counts, row_width=RICH_ROW_WIDTH
        )
    }
