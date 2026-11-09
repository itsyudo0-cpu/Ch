from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

try:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:  # pragma: no cover

    @dataclass
    class InlineKeyboardButton:  # type: ignore[no-redef]
        text: str
        url: str | None = None
        callback_data: str | None = None
        style: str | None = None

    @dataclass
    class InlineKeyboardMarkup:  # type: ignore[no-redef]
        inline_keyboard: list[list[InlineKeyboardButton]]


# Telegram Bot API limits for InlineKeyboardMarkup URL buttons
MAX_BUTTONS_PER_ROW = 8
MAX_TOTAL_BUTTONS = 100
MAX_ROWS = 100
MAX_BUTTON_TEXT_LEN = 64
MAX_URL_LEN = 2048
ALLOWED_SCHEMES = frozenset({"http", "https", "tg"})

# Vote buttons: written as "Text - vote" instead of "Text - https://url".
VOTE_KEYWORD = "vote"
# Telegram callback_data limit is 64 bytes: "v:<token>:<option>" stays far below it.
VOTE_CALLBACK_PREFIX = "v"
PREVIEW_VOTE_TOKEN = "preview"

# Colored buttons (Bot API 9.4+): primary = blue, success = green, danger = red.
# "default" = Telegram's normal (uncolored) button. A button without a stored
# "style" key is shown (and sent) as blue.
STYLE_DEFAULT_KEY = "primary"
STYLE_CYCLE: tuple[str, ...] = ("primary", "success", "danger", "default")
STYLE_EMOJI: dict[str, str] = {
    "primary": "🔵",
    "success": "🟢",
    "danger": "🔴",
    "default": "⚪",
}


def effective_style(btn: dict[str, str]) -> str:
    """Style key actually used for a button (always a key of STYLE_EMOJI)."""
    style = btn.get("style")
    return style if style in STYLE_EMOJI else STYLE_DEFAULT_KEY


def api_style(btn: dict[str, str]) -> str | None:
    """Value for the Telegram `style` field (None = normal, uncolored button)."""
    style = effective_style(btn)
    return None if style == "default" else style


def next_style(current: str) -> str:
    idx = STYLE_CYCLE.index(current) if current in STYLE_CYCLE else -1
    return STYLE_CYCLE[(idx + 1) % len(STYLE_CYCLE)]


def cycle_button_style(
    rows: list[list[dict[str, str]]], row_index: int, col_index: int
) -> list[list[dict[str, str]]]:
    """Switch one button to its next color. Indices are 0-based."""
    if row_index < 0 or row_index >= len(rows):
        raise IndexError(f"Row index {row_index + 1} is out of range.")
    if col_index < 0 or col_index >= len(rows[row_index]):
        raise IndexError(
            f"Button index {col_index + 1} in row {row_index + 1} is out of range."
        )
    updated = [[dict(btn) for btn in row] for row in rows]
    btn = updated[row_index][col_index]
    btn["style"] = next_style(effective_style(btn))
    return updated


# Color tags typed by the admin: "#g Text - url" (prefix) or "Text - url #g" (suffix).
COLOR_TAGS: dict[str, str] = {
    "g": "success",  # green
    "b": "primary",  # blue
    "r": "danger",  # red
    "n": "default",  # plain / uncolored
}
STYLE_TAG: dict[str, str] = {v: k for k, v in COLOR_TAGS.items()}
_TAG_PREFIX_RE = re.compile(r"^#([gbrn])(?=\s)", re.IGNORECASE)
_TAG_SUFFIX_RE = re.compile(r"(?<=\s)#([gbrn])$", re.IGNORECASE)


def extract_color_tag(segment: str) -> tuple[str, str | None]:
    """Strip a #g/#b/#r/#n tag from a button segment -> (clean_segment, style or None)."""
    seg = segment.strip()
    match = _TAG_PREFIX_RE.match(seg)
    if match:
        return seg[match.end() :].strip(), COLOR_TAGS[match.group(1).lower()]
    match = _TAG_SUFFIX_RE.search(seg)
    if match:
        return seg[: match.start()].strip(), COLOR_TAGS[match.group(1).lower()]
    return seg, None


class ButtonParseError(ValueError):
    """Raised when button definition text fails syntax, URL, or limit validation."""


@dataclass(frozen=True, slots=True)
class ParsedButton:
    text: str
    url: str = ""
    vote: str = ""
    style: str = ""

    def to_dict(self) -> dict[str, str]:
        out = (
            {"text": self.text, "vote": self.vote}
            if self.vote
            else {"text": self.text, "url": self.url}
        )
        if self.style:
            out["style"] = self.style
        return out


def is_vote_button(btn: dict[str, str]) -> bool:
    return bool(btn.get("vote"))


def new_vote_token() -> str:
    """Short unique token linking a channel post to its votes (fits callback_data)."""
    return secrets.token_hex(5)


def has_vote_buttons(rows: list[list[dict[str, str]]]) -> bool:
    return any(is_vote_button(btn) for row in rows for btn in row)


def next_vote_id(rows: list[list[dict[str, str]]]) -> int:
    """Stable, never-reused option id (removing a button must not renumber votes)."""
    ids = [int(b["vote"]) for row in rows for b in row if str(b.get("vote", "")).isdigit()]
    return (max(ids) + 1) if ids else 1


def build_vote_callback(token: str, option_id: str | int) -> str:
    return f"{VOTE_CALLBACK_PREFIX}:{token}:{option_id}"


def parse_vote_callback(data: str) -> tuple[str, str] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != VOTE_CALLBACK_PREFIX or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def validate_button_url(url: str) -> str:
    """Validate that a URL uses http, https, or tg:// scheme and is well-formed."""
    cleaned = url.strip()
    if not cleaned:
        raise ButtonParseError("URL cannot be empty.")
    if len(cleaned) > MAX_URL_LEN:
        raise ButtonParseError(
            f"URL exceeds Telegram limit of {MAX_URL_LEN} characters."
        )
    if any(ch.isspace() for ch in cleaned):
        raise ButtonParseError(f"URL '{cleaned}' must not contain whitespace.")

    parsed = urlparse(cleaned)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ButtonParseError(
            f"Invalid URL scheme in '{cleaned}'. Only http://, https://, and tg:// are allowed."
        )

    if scheme in {"http", "https"}:
        if not parsed.netloc or "." not in parsed.netloc:
            raise ButtonParseError(
                f"Invalid HTTP/HTTPS URL '{cleaned}': missing a valid domain name."
            )
        if parsed.netloc.startswith(".") or parsed.netloc.endswith("."):
            raise ButtonParseError(
                f"Invalid HTTP/HTTPS URL '{cleaned}': malformed domain name."
            )
    elif scheme == "tg":
        if not parsed.netloc and not parsed.path:
            raise ButtonParseError(
                f"Invalid tg:// link '{cleaned}': missing target path or domain."
            )

    return cleaned


def parse_buttons_text(
    raw_text: str,
    existing_rows: list[list[dict[str, str]]] | None = None,
) -> list[list[dict[str, str]]]:
    """
    Parse user text into a 2D list of button dicts: [[{"text": ..., "url": ...}, ...], ...].

    Format:
    - One row per non-empty line.
    - Multiple buttons in the same row separated by '|'.
    - Each button formatted as: Text - https://example.com
    - Vote button: Text - vote (one unique vote per user, live counter on the button)
    """
    if not raw_text or not raw_text.strip():
        raise ButtonParseError("Button input cannot be empty.")

    base_rows: list[list[dict[str, str]]] = [
        [dict(btn) for btn in row] for row in (existing_rows or [])
    ]
    total_buttons = sum(len(r) for r in base_rows)
    new_rows: list[list[dict[str, str]]] = []

    lines = raw_text.strip().splitlines()
    for line_idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        segments = [seg.strip() for seg in line.split("|")]
        if any(not seg for seg in segments):
            raise ButtonParseError(
                f"Line {line_idx}: Empty button segment near '|'. "
                "Format each button as 'Text - https://url'."
            )

        if len(segments) > MAX_BUTTONS_PER_ROW:
            raise ButtonParseError(
                f"Line {line_idx}: Too many buttons in one row ({len(segments)}). "
                f"Telegram allows at most {MAX_BUTTONS_PER_ROW} buttons per row."
            )

        row_buttons: list[dict[str, str]] = []
        for btn_idx, segment in enumerate(segments, start=1):
            segment, tag_style = extract_color_tag(segment)
            if " - " not in segment:
                raise ButtonParseError(
                    f"Line {line_idx}, button {btn_idx} ('{segment}'): "
                    "Missing ' - ' separator. Expected format: Text - https://url"
                )

            text_part, url_part = segment.rsplit(" - ", 1)
            btn_text = text_part.strip()
            btn_url_raw = url_part.strip()

            if not btn_text:
                raise ButtonParseError(
                    f"Line {line_idx}, button {btn_idx}: Button text cannot be empty."
                )
            if len(btn_text) > MAX_BUTTON_TEXT_LEN:
                raise ButtonParseError(
                    f"Line {line_idx}, button {btn_idx}: Button text exceeds "
                    f"{MAX_BUTTON_TEXT_LEN} characters ({len(btn_text)} chars)."
                )

            is_vote = btn_url_raw.lower() == VOTE_KEYWORD
            validated_url = "" if is_vote else validate_button_url(btn_url_raw)
            total_buttons += 1
            if total_buttons > MAX_TOTAL_BUTTONS:
                raise ButtonParseError(
                    f"Total buttons exceed Telegram limit of {MAX_TOTAL_BUTTONS} buttons."
                )

            if is_vote:
                vote_id = next_vote_id(base_rows + new_rows + [row_buttons])
                row_buttons.append(
                    ParsedButton(
                        text=btn_text, vote=str(vote_id), style=tag_style or ""
                    ).to_dict()
                )
            else:
                row_buttons.append(
                    ParsedButton(
                        text=btn_text, url=validated_url, style=tag_style or ""
                    ).to_dict()
                )

        new_rows.append(row_buttons)

    if not new_rows:
        raise ButtonParseError("No valid buttons found in input.")

    combined = base_rows + new_rows
    if len(combined) > MAX_ROWS:
        raise ButtonParseError(
            f"Total button rows ({len(combined)}) exceed limit of {MAX_ROWS} rows."
        )

    return combined


def remove_button_by_position(
    rows: list[list[dict[str, str]]],
    row_index: int,
    col_index: int | None = None,
) -> list[list[dict[str, str]]]:
    """
    Remove either an entire row (if col_index is None) or a single button at (row_index, col_index).
    Indices are 0-based. Automatically removes empty rows.
    """
    if row_index < 0 or row_index >= len(rows):
        raise IndexError(f"Row index {row_index + 1} is out of range.")

    updated = [[dict(btn) for btn in row] for row in rows]
    if col_index is None:
        updated.pop(row_index)
    else:
        target_row = updated[row_index]
        if col_index < 0 or col_index >= len(target_row):
            raise IndexError(
                f"Button index {col_index + 1} in row {row_index + 1} is out of range."
            )
        target_row.pop(col_index)
        if not target_row:
            updated.pop(row_index)

    return updated


def format_buttons_dsl(rows: list[list[dict[str, str]]]) -> str:
    """Convert stored 2D button rows back into the human-readable DSL string."""
    if not rows:
        return ""
    lines: list[str] = []
    for row in rows:
        parts: list[str] = []
        for btn in row:
            style = effective_style(btn)
            tag = f"#{STYLE_TAG[style]} " if style != STYLE_DEFAULT_KEY else ""
            target = VOTE_KEYWORD if is_vote_button(btn) else btn["url"]
            parts.append(f"{tag}{btn['text']} - {target}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _vote_label(text: str, count: int) -> str:
    if count <= 0:
        return text
    suffix = f" · {count}"
    return text[: MAX_BUTTON_TEXT_LEN - len(suffix)] + suffix


def build_inline_keyboard(
    rows: list[list[dict[str, str]]],
    vote_token: str | None = None,
    vote_counts: dict[str, int] | None = None,
) -> InlineKeyboardMarkup | None:
    """
    Build a classic Telegram InlineKeyboardMarkup.

    URL buttons become url buttons. Vote buttons become callback buttons
    (`v:<token>:<option_id>`) with the live counter appended to the label.
    Vote buttons are skipped when no `vote_token` is available.
    """
    if not rows:
        return None
    counts = vote_counts or {}
    inline_keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        kb_row: list[InlineKeyboardButton] = []
        for btn in row:
            if not btn.get("text"):
                continue
            if is_vote_button(btn):
                if not vote_token:
                    continue
                kb_row.append(
                    InlineKeyboardButton(
                        text=_vote_label(btn["text"], counts.get(btn["vote"], 0)),
                        callback_data=build_vote_callback(vote_token, btn["vote"]),
                        style=api_style(btn),
                    )
                )
            elif btn.get("url"):
                kb_row.append(
                    InlineKeyboardButton(
                        text=btn["text"], url=btn["url"], style=api_style(btn)
                    )
                )
        if kb_row:
            inline_keyboard.append(kb_row)
    if not inline_keyboard:
        return None
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_url_inline_keyboard(
    rows: list[list[dict[str, str]]],
) -> InlineKeyboardMarkup | None:
    """Backward compatible alias: URL buttons only (vote buttons are skipped)."""
    return build_inline_keyboard(rows)
