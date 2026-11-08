from __future__ import annotations

import unittest

from bot.utils.button_parser import parse_buttons_text
from bot.utils.rich_post import (
    build_rich_blocks,
    build_rich_message,
    entities_to_rich_text,
    rich_button_for,
)


class TestEntitiesToRichText(unittest.TestCase):
    def test_plain_text(self) -> None:
        self.assertEqual(entities_to_rich_text("Hello", []), "Hello")

    def test_bold_and_link_with_emoji_utf16_offsets(self) -> None:
        text = "Hi \U0001F600 bold and link"  # emoji = 2 UTF-16 units
        ents = [
            {"type": "bold", "offset": 6, "length": 4},
            {"type": "text_link", "offset": 15, "length": 4, "url": "https://x.com"},
        ]
        self.assertEqual(
            entities_to_rich_text(text, ents),
            [
                "Hi \U0001F600 ",
                {"type": "bold", "text": "bold"},
                " and ",
                {"type": "url", "text": "link", "url": "https://x.com"},
            ],
        )

    def test_nested_entities(self) -> None:
        ents = [
            {"type": "bold", "offset": 0, "length": 2},
            {"type": "italic", "offset": 0, "length": 1},
        ]
        self.assertEqual(
            entities_to_rich_text("ab", ents),
            {"type": "bold", "text": [{"type": "italic", "text": "a"}, "b"]},
        )

    def test_partially_overlapping_entity_is_ignored_not_crashing(self) -> None:
        ents = [
            {"type": "bold", "offset": 0, "length": 3},
            {"type": "italic", "offset": 2, "length": 3},
        ]
        result = entities_to_rich_text("abcde", ents)
        self.assertEqual(result[0], {"type": "bold", "text": "abc"})


class TestRichBlocks(unittest.TestCase):
    def test_text_post_with_url_and_vote_buttons(self) -> None:
        rows = parse_buttons_text("Yes - vote | Site - https://example.com\nNo - vote")
        content = {"content_type": "text", "text": "Poll?", "entities": []}
        blocks = build_rich_blocks(content, rows, "tok", {"1": 4})
        self.assertEqual(blocks[0], {"type": "paragraph", "text": "Poll?"})
        self.assertEqual(blocks[1]["type"], "buttons")
        self.assertEqual(
            blocks[1]["buttons"],
            [
                {"text": "Yes \u00b7 4", "callback_data": "v:tok:1", "style": "primary"},
                {"text": "Site", "url": "https://example.com", "style": "primary"},
            ],
        )
        self.assertEqual(blocks[2]["buttons"], [{"text": "No", "callback_data": "v:tok:2", "style": "primary"}])

    def test_photo_post_has_media_block_first(self) -> None:
        rows = parse_buttons_text("Site - https://example.com")
        content = {"content_type": "photo", "file_id": "FID", "text": "cap", "entities": []}
        blocks = build_rich_blocks(content, rows)
        self.assertEqual(blocks[0], {"type": "photo", "photo": {"type": "photo", "media": "FID"}})
        self.assertEqual(blocks[1]["type"], "paragraph")
        self.assertEqual(blocks[2]["type"], "buttons")

    def test_each_button_has_exactly_one_action(self) -> None:
        for raw in ("A - vote", "B - https://example.com"):
            btn = parse_buttons_text(raw)[0][0]
            rich = rich_button_for(btn, "tok", {})
            assert rich is not None
            self.assertEqual(len({"url", "callback_data"} & rich.keys()), 1)

    def test_vote_button_skipped_without_token(self) -> None:
        btn = parse_buttons_text("A - vote")[0][0]
        self.assertIsNone(rich_button_for(btn, None, {}))

    def test_message_uses_blocks_mode_only(self) -> None:
        rows = parse_buttons_text("Site - https://example.com")
        msg = build_rich_message({"content_type": "text", "text": "x", "entities": []}, rows)
        self.assertEqual(list(msg.keys()), ["blocks"])


if __name__ == "__main__":
    unittest.main()
