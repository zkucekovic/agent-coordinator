"""Extended unit tests for human_prompt.py — _prompt_tui view path and _prompt_plain."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_coordinator.infrastructure.human_prompt import _prompt_plain, _prompt_tui


def _make_display(side_effects):
    display = MagicMock()
    display._theme.color_warning = ""
    display._theme.color_success = ""
    display._theme.text_dim = ""
    display._theme.text_secondary = ""
    display._cols = 80
    display.show_error_dialog.side_effect = side_effects
    display._append_content = MagicMock()
    display.read_input = MagicMock(return_value="")
    display.with_editor = MagicMock()
    return display


class TestPromptTuiViewPath(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_view_then_quit_without_handoff_returns_quit(self):
        """'v' loops back without appending handoff lines when file absent, 'q' returns quit."""
        display = _make_display(["v", "q"])
        handoff = self.tmp_path / "handoff.md"
        result = _prompt_tui(handoff, "task-1", "blocked", display)
        self.assertEqual(result, "quit")
        self.assertEqual(display.show_error_dialog.call_count, 2)

    def test_view_with_existing_handoff_appends_content(self):
        """'v' on existing handoff.md appends its lines to display, then 'q' quits."""
        handoff = self.tmp_path / "handoff.md"
        handoff.write_text("line one\nline two\nline three\n")
        display = _make_display(["v", "q"])
        result = _prompt_tui(handoff, "task-2", "waiting", display)
        self.assertEqual(result, "quit")
        appended = [str(c) for c in display._append_content.call_args_list]
        self.assertTrue(any("line one" in s for s in appended))
        self.assertTrue(any("line two" in s for s in appended))

    def test_view_shows_header_line(self):
        """When viewing, the header '── handoff.md' is appended."""
        handoff = self.tmp_path / "handoff.md"
        handoff.write_text("content\n")
        display = _make_display(["v", "q"])
        _prompt_tui(handoff, "task-3", "paused", display)
        appended = [str(c) for c in display._append_content.call_args_list]
        self.assertTrue(any("handoff.md" in s for s in appended))

    def test_view_loops_back_to_dialog(self):
        """After 'v', dialog is shown again."""
        handoff = self.tmp_path / "handoff.md"
        handoff.write_text("data\n")
        display = _make_display(["v", "v", "q"])
        result = _prompt_tui(handoff, "t", "s", display)
        self.assertEqual(result, "quit")
        self.assertEqual(display.show_error_dialog.call_count, 3)

    def test_respond_empty_then_quit(self):
        """'r' with no input warns and loops; then 'q' returns quit."""
        display = _make_display(["r", "q"])
        display.read_input.side_effect = ["", ""]  # blank line ends input; empty response
        handoff = self.tmp_path / "handoff.md"
        result = _prompt_tui(handoff, "task-4", "pending", display)
        self.assertEqual(result, "quit")
        appended = [str(c) for c in display._append_content.call_args_list]
        self.assertTrue(any("No response" in s for s in appended))


class TestPromptPlain(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_quit_returns_quit(self):
        with patch("agent_coordinator.infrastructure.enhanced_input.enhanced_choice", return_value="q"):
            result = _prompt_plain(self.tmp_path / "handoff.md", "task-1", "blocked")
        self.assertEqual(result, "quit")

    def test_view_then_quit(self):
        """'v' shows file content and loops; 'q' exits."""
        handoff = self.tmp_path / "handoff.md"
        handoff.write_text("important line\n")
        choice_seq = iter(["v", "q"])
        with (
            patch(
                "agent_coordinator.infrastructure.enhanced_input.enhanced_choice",
                side_effect=lambda *a, **kw: next(choice_seq),
            ),
            patch(
                "agent_coordinator.infrastructure.enhanced_input.enhanced_input",
                return_value="",
            ),
        ):
            result = _prompt_plain(handoff, "task-2", "waiting")
        self.assertEqual(result, "quit")

    def test_view_nonexistent_handoff_then_quit(self):
        """'v' on missing file doesn't crash; then 'q' exits."""
        choice_seq = iter(["v", "q"])
        with (
            patch(
                "agent_coordinator.infrastructure.enhanced_input.enhanced_choice",
                side_effect=lambda *a, **kw: next(choice_seq),
            ),
            patch(
                "agent_coordinator.infrastructure.enhanced_input.enhanced_input",
                return_value="",
            ),
        ):
            result = _prompt_plain(self.tmp_path / "missing.md", "task-3", "pending")
        self.assertEqual(result, "quit")

    def test_respond_empty_reloops_then_quit(self):
        """'r' with empty response prints warning and loops; 'q' exits."""
        choice_seq = iter(["r", "q"])
        with (
            patch(
                "agent_coordinator.infrastructure.enhanced_input.enhanced_choice",
                side_effect=lambda *a, **kw: next(choice_seq),
            ),
            patch(
                "builtins.input",
                return_value="",
            ),
        ):
            result = _prompt_plain(self.tmp_path / "handoff.md", "task-5", "pending")
        self.assertEqual(result, "quit")

    def test_respond_with_content_returns_continue(self):
        """'r' with actual response writes handoff and returns 'continue'."""
        handoff = self.tmp_path / "handoff.md"
        input_seq = iter(["my response", ""])  # response text, then blank line to finish
        choice_seq = iter(["r"])
        with (
            patch(
                "agent_coordinator.infrastructure.enhanced_input.enhanced_choice",
                side_effect=lambda *a, **kw: next(choice_seq),
            ),
            patch(
                "builtins.input",
                side_effect=lambda *a: next(input_seq),
            ),
            patch(
                "agent_coordinator.infrastructure.enhanced_input.enhanced_input",
                return_value="architect",
            ),
        ):
            result = _prompt_plain(handoff, "task-6", "pending")
        self.assertEqual(result, "continue")
        self.assertIn("my response", handoff.read_text())


if __name__ == "__main__":
    unittest.main()
