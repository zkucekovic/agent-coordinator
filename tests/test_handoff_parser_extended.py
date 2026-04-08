"""Extended tests for agent_coordinator/handoff_parser.py.

Targets uncovered branches:
- Line 58:  non-bullet list item in a list-field section gets appended
- Lines 83-84: ROLE present but empty after strip → "ROLE field must not be empty"
- Line 96:  NEXT present but empty → "NEXT field must not be empty"
- Lines 135-137: extract_latest when all blocks are invalid returns last errors
"""

from __future__ import annotations

import unittest

from agent_coordinator.handoff_parser import _parse_list_field, extract_latest, parse_block

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_block(**overrides) -> str:
    """Build a minimal valid block text, with any field overridable."""
    defaults = {
        "ROLE": "architect",
        "STATUS": "continue",
        "NEXT": "developer",
        "TASK_ID": "task-001",
        "TITLE": "Test title",
        "SUMMARY": "Test summary",
    }
    defaults.update(overrides)
    lines = [f"{k}: {v}" for k, v in defaults.items()]
    return "\n".join(lines) + "\n"


# ── _parse_list_field (line 58) ────────────────────────────────────────────────


class TestParseListFieldNonBulletLine(unittest.TestCase):
    """Line 58: a non-empty, non-bullet, non-comment line inside a list section
    is appended to items without stripping a leading '- '."""

    def test_plain_text_line_in_section_is_included(self):
        # An item that does NOT start with "- " should still be captured.
        block = "ROLE: architect\nACCEPTANCE:\nplain item without dash\nSTATUS: continue\n"
        items = _parse_list_field(block, "ACCEPTANCE")
        self.assertIn("plain item without dash", items)

    def test_mixed_bullet_and_plain_lines(self):
        block = "ROLE: architect\nACCEPTANCE:\n- bullet item\nplain item\nSTATUS: continue\n"
        items = _parse_list_field(block, "ACCEPTANCE")
        self.assertIn("bullet item", items)
        self.assertIn("plain item", items)

    def test_comment_lines_skipped(self):
        # Lines starting with '#' should NOT be included.
        block = "ROLE: architect\nACCEPTANCE:\n# this is a comment\n- real item\nSTATUS: continue\n"
        items = _parse_list_field(block, "ACCEPTANCE")
        self.assertNotIn("# this is a comment", items)
        self.assertIn("real item", items)

    def test_empty_lines_skipped(self):
        block = "ROLE: architect\nACCEPTANCE:\n\n- real item\n\nSTATUS: continue\n"
        items = _parse_list_field(block, "ACCEPTANCE")
        self.assertNotIn("", items)
        self.assertIn("real item", items)


# ── parse_block empty ROLE (lines 83-84) ──────────────────────────────────────


class TestParseBlockEmptyRole(unittest.TestCase):
    """Lines 83-84: ROLE field present but value is whitespace → error.

    The regex ``\\s*(.+)$`` backtracks: ``\\s*`` consumes all-but-one space,
    letting ``(.+)`` capture the remaining space; ``.strip()`` then yields "".
    This only works when ROLE is the last field (no trailing newline), otherwise
    ``\\s*`` spans the newline and ``(.+)`` captures the next line instead.
    """

    # ROLE is placed last with trailing spaces and NO trailing newline so that
    # \s* cannot span into the next line's content.
    _BLOCK = (
        "STATUS: continue\n"
        "NEXT: developer\n"
        "TASK_ID: task-001\n"
        "TITLE: Test\n"
        "SUMMARY: Summary\n"
        "ROLE:   "  # last field, no trailing newline → (.+) captures " ", strip → ""
    )

    def test_whitespace_role_returns_none(self):
        msg, _errors = parse_block(self._BLOCK)
        self.assertIsNone(msg)

    def test_empty_role_error_message(self):
        msg, errors = parse_block(self._BLOCK)
        self.assertIsNone(msg)
        role_errors = [e for e in errors if "ROLE" in e]
        self.assertTrue(len(role_errors) > 0, f"No ROLE error found in: {errors}")


# ── parse_block empty NEXT (line 96) ──────────────────────────────────────────


class TestParseBlockEmptyNext(unittest.TestCase):
    """Line 96: NEXT field present but value is whitespace → error.

    Same regex-backtracking mechanics as the empty-ROLE case: NEXT must be the
    last field with no trailing newline so that ``\\s*`` cannot span to the next
    line.
    """

    _BLOCK = (
        "ROLE: architect\n"
        "STATUS: continue\n"
        "TASK_ID: task-001\n"
        "TITLE: Test\n"
        "SUMMARY: Summary\n"
        "NEXT:   "  # last field, no trailing newline
    )

    def test_whitespace_next_returns_none(self):
        msg, _errors = parse_block(self._BLOCK)
        self.assertIsNone(msg)

    def test_empty_next_error_message(self):
        msg, errors = parse_block(self._BLOCK)
        self.assertIsNone(msg)
        self.assertTrue(
            any("NEXT" in e for e in errors),
            f"Expected error mentioning NEXT, got: {errors}",
        )


# ── extract_latest all-invalid blocks (lines 135-137) ─────────────────────────


class TestExtractLatestAllInvalid(unittest.TestCase):
    """Lines 135-137: all blocks fail to parse → returns errors from the last
    block processed in the reversed iteration (= first block in the content).

    extract_latest iterates reversed(blocks), so 'last_errors' ends up holding
    errors from the first block in the content (processed last).
    """

    # Block 1 (first in content, processed LAST in reversed loop):
    #   missing NEXT, TASK_ID, TITLE, SUMMARY
    # Block 2 (last in content, processed FIRST in reversed loop):
    #   has invalid STATUS
    ALL_INVALID = (
        "---HANDOFF---\n"
        "ROLE: architect\n"
        "STATUS: continue\n"
        # missing NEXT, TASK_ID, TITLE, SUMMARY
        "\n---END---\n"
        "\n"
        "---HANDOFF---\n"
        "ROLE: developer\n"
        "STATUS: bogus_status\n"
        "NEXT: architect\n"
        "TASK_ID: task-002\n"
        "TITLE: Second block\n"
        "SUMMARY: Also invalid\n"
        "\n---END---\n"
    )

    def test_returns_none_when_all_invalid(self):
        msg, _errors = extract_latest(self.ALL_INVALID)
        self.assertIsNone(msg)

    def test_returns_errors_from_last_block(self):
        _msg, errors = extract_latest(self.ALL_INVALID)
        self.assertTrue(len(errors) > 0, "Expected errors but got none")

    def test_errors_come_from_first_content_block(self):
        # The first block is processed last in the reversed loop → its errors
        # end up in last_errors and are returned.
        _msg, errors = extract_latest(self.ALL_INVALID)
        self.assertTrue(
            any("Missing required field" in e for e in errors),
            f"Expected 'Missing required field' errors from first block, got: {errors}",
        )

    def test_no_blocks_content(self):
        msg, errors = extract_latest("# just prose\nno blocks here\n")
        self.assertIsNone(msg)
        self.assertTrue(len(errors) > 0)

    def test_single_invalid_block(self):
        content = (
            "---HANDOFF---\n"
            "ROLE: architect\n"
            # missing all required fields
            "\n---END---\n"
        )
        msg, errors = extract_latest(content)
        self.assertIsNone(msg)
        self.assertTrue(len(errors) > 0)


if __name__ == "__main__":
    unittest.main()
