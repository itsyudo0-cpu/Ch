from __future__ import annotations

import unittest

from bot.utils.button_parser import (
    MAX_BUTTON_TEXT_LEN,
    MAX_BUTTONS_PER_ROW,
    MAX_TOTAL_BUTTONS,
    ButtonParseError,
    build_inline_keyboard,
    build_url_inline_keyboard,
    build_vote_callback,
    has_vote_buttons,
    new_vote_token,
    parse_vote_callback,
    format_buttons_dsl,
    parse_buttons_text,
    remove_button_by_position,
    validate_button_url,
)


class TestButtonParser(unittest.TestCase):
    def test_single_row_single_button(self) -> None:
        raw = "Official Website - https://example.com"
        rows = parse_buttons_text(raw)
        self.assertEqual(
            rows,
            [[{"text": "Official Website", "url": "https://example.com"}]],
        )

    def test_multiple_rows_and_pipe_separated_buttons(self) -> None:
        raw = (
            "Read Blog - https://example.com/blog\n"
            "GitHub - https://github.com/org/repo | Telegram - tg://resolve?domain=telegram\n"
            "\n"
            "HTTP Link - http://legacy.example.org/path?query=1"
        )
        rows = parse_buttons_text(raw)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(rows[0]), 1)
        self.assertEqual(len(rows[1]), 2)
        self.assertEqual(rows[1][0]["text"], "GitHub")
        self.assertEqual(rows[1][1]["url"], "tg://resolve?domain=telegram")
        self.assertEqual(rows[2][0]["url"], "http://legacy.example.org/path?query=1")

    def test_button_text_containing_hyphens(self) -> None:
        raw = "Part 1 - Getting Started - Guide - https://docs.example.com/start"
        rows = parse_buttons_text(raw)
        self.assertEqual(rows[0][0]["text"], "Part 1 - Getting Started - Guide")
        self.assertEqual(rows[0][0]["url"], "https://docs.example.com/start")

    def test_append_to_existing_rows(self) -> None:
        existing = [[{"text": "First", "url": "https://first.example.com"}]]
        updated = parse_buttons_text(
            "Second - https://second.example.com", existing_rows=existing
        )
        self.assertEqual(len(updated), 2)
        self.assertEqual(updated[0][0]["text"], "First")
        self.assertEqual(updated[1][0]["text"], "Second")

    def test_reject_invalid_url_schemes(self) -> None:
        for invalid in [
            "Click - javascript:alert(1)",
            "FTP - ftp://files.example.com/archive.zip",
            "Mail - mailto:admin@example.com",
            "No Scheme - www.example.com",
        ]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ButtonParseError):
                    parse_buttons_text(invalid)

    def test_reject_malformed_urls(self) -> None:
        for malformed in [
            "https://",
            "http://nodot",
            "https://.leadingdot.com",
            "https://trailingdot.com.",
            "tg://",
            "https://example.com/path with spaces",
        ]:
            with self.subTest(malformed=malformed):
                with self.assertRaises(ButtonParseError):
                    validate_button_url(malformed)

    def test_reject_missing_separator_or_empty_parts(self) -> None:
        for bad_input in [
            "",
            "   \n  ",
            "MissingSeparator https://example.com",
            " - https://example.com",
            "Valid - https://example.com | ",
            " | Valid - https://example.com",
        ]:
            with self.subTest(bad_input=bad_input):
                with self.assertRaises(ButtonParseError):
                    parse_buttons_text(bad_input)

    def test_enforce_max_buttons_per_row(self) -> None:
        too_many_in_row = " | ".join(
            f"B{i} - https://example.com/{i}" for i in range(MAX_BUTTONS_PER_ROW + 1)
        )
        with self.assertRaises(ButtonParseError):
            parse_buttons_text(too_many_in_row)

    def test_enforce_max_button_text_length(self) -> None:
        long_text = "A" * (MAX_BUTTON_TEXT_LEN + 1)
        with self.assertRaises(ButtonParseError):
            parse_buttons_text(f"{long_text} - https://example.com")

    def test_enforce_max_total_buttons(self) -> None:
        lines = [
            f"Btn {i} - https://example.com/{i}"
            for i in range(MAX_TOTAL_BUTTONS + 1)
        ]
        with self.assertRaises(ButtonParseError):
            parse_buttons_text("\n".join(lines))

    def test_remove_button_and_row_cleanup(self) -> None:
        rows = parse_buttons_text(
            "One - https://example.com/1 | Two - https://example.com/2\n"
            "Three - https://example.com/3"
        )
        after_first_rm = remove_button_by_position(rows, 0, 0)
        self.assertEqual(len(after_first_rm), 2)
        self.assertEqual(after_first_rm[0][0]["text"], "Two")

        after_row_empty = remove_button_by_position(after_first_rm, 0, 0)
        self.assertEqual(len(after_row_empty), 1)
        self.assertEqual(after_row_empty[0][0]["text"], "Three")

    def test_roundtrip_dsl_and_keyboard_builder(self) -> None:
        rows = parse_buttons_text(
            "Docs - https://example.com/docs | Support - tg://resolve?domain=support"
        )
        dsl = format_buttons_dsl(rows)
        self.assertEqual(
            dsl,
            "Docs - https://example.com/docs | Support - tg://resolve?domain=support",
        )
        kb = build_url_inline_keyboard(rows)
        self.assertIsNotNone(kb)
        assert kb is not None
        self.assertEqual(len(kb.inline_keyboard), 1)
        self.assertEqual(len(kb.inline_keyboard[0]), 2)
        self.assertEqual(kb.inline_keyboard[0][0].text, "Docs")
        self.assertEqual(kb.inline_keyboard[0][0].url, "https://example.com/docs")


if __name__ == "__main__":
    unittest.main()


class TestVoteButtons(unittest.TestCase):
    def test_vote_keyword_creates_vote_buttons_with_stable_ids(self) -> None:
        rows = parse_buttons_text("👍 Yes - vote | 👎 No - vote\nSite - https://example.com")
        self.assertEqual(rows[0], [
            {"text": "👍 Yes", "vote": "1"},
            {"text": "👎 No", "vote": "2"},
        ])
        self.assertTrue(has_vote_buttons(rows))

    def test_ids_are_never_reused_after_removal(self) -> None:
        rows = parse_buttons_text("A - vote | B - vote")
        rows = remove_button_by_position(rows, 0, 0)
        rows = parse_buttons_text("C - vote", existing_rows=rows)
        self.assertEqual([b["vote"] for r in rows for b in r], ["2", "3"])

    def test_dsl_roundtrip_and_keyboard_counters(self) -> None:
        rows = parse_buttons_text("Yes - vote | No - vote")
        self.assertEqual(format_buttons_dsl(rows), "Yes - vote | No - vote")
        kb = build_inline_keyboard(rows, vote_token="tok123", vote_counts={"1": 7})
        assert kb is not None
        first, second = kb.inline_keyboard[0]
        self.assertEqual(first.text, "Yes · 7")
        self.assertEqual(first.callback_data, "v:tok123:1")
        self.assertEqual(second.text, "No")

    def test_vote_buttons_skipped_without_token_and_callback_roundtrip(self) -> None:
        rows = parse_buttons_text("Yes - vote")
        self.assertIsNone(build_url_inline_keyboard(rows))
        self.assertEqual(parse_vote_callback("v:tok123:2"), ("tok123", "2"))
        self.assertIsNone(parse_vote_callback("menu:home"))
        self.assertLessEqual(len(build_vote_callback(new_vote_token(), 99).encode()), 64)

    def test_long_vote_label_stays_within_telegram_limit(self) -> None:
        rows = parse_buttons_text(f"{'A' * MAX_BUTTON_TEXT_LEN} - vote")
        kb = build_inline_keyboard(rows, vote_token="t", vote_counts={"1": 12345})
        assert kb is not None
        self.assertLessEqual(len(kb.inline_keyboard[0][0].text), MAX_BUTTON_TEXT_LEN)
