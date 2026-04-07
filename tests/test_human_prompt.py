"""Unit tests for human_prompt helpers."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_coordinator.infrastructure.human_prompt import (
    _write_human_handoff,
    _prompt_tui,
    _prompt_plain,
)


def _make_display(choice="q", read_input_side_effect=None):
    display = MagicMock()
    display._theme.color_warning = ""
    display._theme.color_success = ""
    display._theme.text_dim = ""
    display._theme.text_secondary = ""
    display._cols = 80
    display.show_error_dialog.return_value = choice
    display._append_content = MagicMock()
    if read_input_side_effect is not None:
        display.read_input.side_effect = read_input_side_effect
    display.with_editor = MagicMock()
    return display


class TestWriteHumanHandoff(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_creates_file_with_expected_content(self):
        handoff = self.tmp_path / "handoff.md"
        _write_human_handoff(handoff, "task-1", "my response", "architect")
        content = handoff.read_text()
        self.assertIn("---HANDOFF---", content)
        self.assertIn("NEXT: architect", content)
        self.assertIn("my response", content)

    def test_appends_second_block(self):
        handoff = self.tmp_path / "handoff.md"
        _write_human_handoff(handoff, "task-1", "first response", "architect")
        _write_human_handoff(handoff, "task-1", "second response", "developer")
        content = handoff.read_text()
        self.assertEqual(content.count("---HANDOFF---"), 2)
        self.assertIn("first response", content)
        self.assertIn("second response", content)


class TestPromptTui(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_quit_returns_quit(self):
        display = _make_display(choice="q")
        result = _prompt_tui(self.tmp_path / "handoff.md", "task-1", "blocked", display)
        self.assertEqual(result, "quit")

    def test_respond_writes_handoff_and_returns_continue(self):
        display = _make_display(choice="r", read_input_side_effect=["my answer", "", "architect"])
        handoff = self.tmp_path / "handoff.md"
        result = _prompt_tui(handoff, "task-1", "blocked", display)
        self.assertEqual(result, "continue")
        content = handoff.read_text()
        self.assertIn("my answer", content)
        self.assertIn("NEXT: architect", content)

    def test_edit_calls_with_editor_and_returns_continue(self):
        display = _make_display(choice="e")
        handoff = self.tmp_path / "handoff.md"
        result = _prompt_tui(handoff, "task-1", "blocked", display)
        self.assertEqual(result, "continue")
        display.with_editor.assert_called_once_with(handoff)


if __name__ == "__main__":
    unittest.main()
