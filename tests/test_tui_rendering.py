"""Unit tests for Screen rendering methods in agent_coordinator/infrastructure/tui.py."""

import io
import unittest
from unittest.mock import patch

from agent_coordinator.infrastructure.tui import AgentState, Screen


def make_screen() -> tuple[Screen, io.StringIO]:
    """Create a Screen configured for testing (no real TTY required)."""
    s = io.StringIO()
    s.isatty = lambda: False  # type: ignore[method-assign]
    screen = Screen(stream=s)
    # Manually enter "active" state without touching the real terminal
    screen._active = True
    screen._rows = 24
    screen._cols = 80
    screen._content_rows = 20
    screen._agents = ["architect", "developer"]
    screen._workspace = "/ws"
    screen._max_turns = 30
    screen._current_turn = 3
    screen._paused = False
    screen._agent_states = {
        "architect": AgentState.IDLE,
        "developer": AgentState.RUNNING,
    }
    return screen, s


# ── _render_header ─────────────────────────────────────────────────────────────


class TestRenderHeader(unittest.TestCase):
    def test_contains_title(self):
        screen, _ = make_screen()
        result = screen._render_header()
        self.assertIn("AGENT COORDINATOR", result)

    def test_contains_escape_codes(self):
        screen, _ = make_screen()
        result = screen._render_header()
        self.assertIn("\033", result)

    def test_paused_contains_paused_text(self):
        screen, _ = make_screen()
        screen._paused = True
        result = screen._render_header()
        self.assertIn("PAUSED", result)

    def test_not_paused_no_paused_text(self):
        screen, _ = make_screen()
        screen._paused = False
        result = screen._render_header()
        self.assertNotIn("PAUSED", result)

    def test_contains_turn_info(self):
        screen, _ = make_screen()
        result = screen._render_header()
        self.assertIn("3/30", result)


# ── _render_separator ──────────────────────────────────────────────────────────


class TestRenderSeparator(unittest.TestCase):
    def test_contains_separator_char(self):
        screen, _ = make_screen()
        result = screen._render_separator()
        self.assertIn("─", result)

    def test_returns_non_empty_string(self):
        screen, _ = make_screen()
        result = screen._render_separator()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


# ── _render_status_bar ─────────────────────────────────────────────────────────


class TestRenderStatusBar(unittest.TestCase):
    def test_returns_non_empty(self):
        screen, _ = make_screen()
        result = screen._render_status_bar()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_contains_agent_names(self):
        screen, _ = make_screen()
        result = screen._render_status_bar()
        self.assertIn("architect", result)
        self.assertIn("developer", result)


# ── _render_content_block ──────────────────────────────────────────────────────


class TestRenderContentBlock(unittest.TestCase):
    def test_returns_string(self):
        screen, _ = make_screen()
        result = screen._render_content_block()
        self.assertIsInstance(result, str)

    def test_with_lines_renders_them(self):
        screen, _ = make_screen()
        screen._lines = ["hello world", "second line"]
        result = screen._render_content_block()
        self.assertIn("hello world", result)
        self.assertIn("second line", result)

    def test_empty_lines_still_returns_string(self):
        screen, _ = make_screen()
        screen._lines = []
        result = screen._render_content_block()
        self.assertIsInstance(result, str)


# ── _append_content ────────────────────────────────────────────────────────────


class TestAppendContent(unittest.TestCase):
    def test_single_append_adds_to_lines(self):
        screen, _ = make_screen()
        screen._append_content("hello")
        self.assertIn("hello", screen._lines)

    def test_multiple_appends_grow_lines(self):
        screen, _ = make_screen()
        initial_len = len(screen._lines)
        screen._append_content("first")
        screen._append_content("second")
        screen._append_content("third")
        self.assertEqual(len(screen._lines), initial_len + 3)


# ── _full_render ───────────────────────────────────────────────────────────────


class TestFullRender(unittest.TestCase):
    def test_no_exception_writes_to_stream(self):
        screen, s = make_screen()
        screen._full_render()
        self.assertTrue(len(s.getvalue()) > 0)

    def test_output_contains_title(self):
        screen, s = make_screen()
        screen._full_render()
        self.assertIn("AGENT COORDINATOR", s.getvalue())


# ── start_agent_turn ───────────────────────────────────────────────────────────


class TestStartAgentTurn(unittest.TestCase):
    def test_sets_current_agent(self):
        screen, _ = make_screen()
        screen.start_agent_turn("architect", "copilot", "task-1", "continue")
        self.assertEqual(screen._current_agent, "architect")

    def test_increments_current_turn(self):
        screen, _ = make_screen()
        initial_turn = screen._current_turn
        screen.start_agent_turn("architect", "copilot", "task-1", "continue")
        self.assertEqual(screen._current_turn, initial_turn + 1)

    def test_sets_agent_state_to_running(self):
        screen, _ = make_screen()
        screen.start_agent_turn("architect", "copilot", "task-1", "continue")
        self.assertEqual(screen._agent_states["architect"], AgentState.RUNNING)


# ── finish_agent_turn ──────────────────────────────────────────────────────────


class TestFinishAgentTurn(unittest.TestCase):
    def test_success_does_not_raise(self):
        screen, _ = make_screen()
        screen._current_agent = "architect"
        screen.finish_agent_turn(True, "done", "developer")

    def test_failure_does_not_raise(self):
        screen, _ = make_screen()
        screen._current_agent = "architect"
        screen.finish_agent_turn(False)

    def test_success_sets_agent_done(self):
        screen, _ = make_screen()
        screen._current_agent = "architect"
        screen.finish_agent_turn(True, "plan_complete", "")
        self.assertEqual(screen._agent_states["architect"], AgentState.DONE)

    def test_failure_sets_agent_error(self):
        screen, _ = make_screen()
        screen._current_agent = "architect"
        screen.finish_agent_turn(False)
        self.assertEqual(screen._agent_states["architect"], AgentState.ERROR)


# ── update_output ──────────────────────────────────────────────────────────────


class TestUpdateOutput(unittest.TestCase):
    def test_active_appends_to_lines(self):
        screen, _ = make_screen()
        initial = len(screen._lines)
        screen.update_output("some text")
        self.assertGreater(len(screen._lines), initial)

    def test_multiline_text_appends_multiple(self):
        screen, _ = make_screen()
        initial = len(screen._lines)
        screen.update_output("line one\nline two\nline three")
        self.assertGreater(len(screen._lines), initial + 1)


# ── close ──────────────────────────────────────────────────────────────────────


class TestClose(unittest.TestCase):
    def test_inactive_is_noop(self):
        screen, _ = make_screen()
        screen._active = False
        screen.close()
        self.assertFalse(screen._active)

    def test_inactive_does_not_raise(self):
        screen, _ = make_screen()
        screen._active = False
        try:
            screen.close()
        except Exception as exc:
            self.fail(f"close() raised unexpectedly: {exc}")


# ── set_paused ─────────────────────────────────────────────────────────────────


class TestSetPaused(unittest.TestCase):
    def test_set_true(self):
        screen, _ = make_screen()
        screen.set_paused(True)
        self.assertTrue(screen._paused)

    def test_set_false(self):
        screen, _ = make_screen()
        screen._paused = True
        screen.set_paused(False)
        self.assertFalse(screen._paused)

    def test_toggle(self):
        screen, _ = make_screen()
        screen.set_paused(True)
        screen.set_paused(False)
        self.assertFalse(screen._paused)


# ── show_error_dialog ──────────────────────────────────────────────────────────


class TestShowErrorDialog(unittest.TestCase):
    def test_fallback_when_inactive_returns_chosen_key(self):
        screen, _ = make_screen()
        screen._active = False
        with patch("sys.stderr") as _mock_err, patch("builtins.input", return_value="q"):
            result = screen.show_error_dialog("Title", "something went wrong", [("q", "Quit")])
        self.assertEqual(result, "q")

    def test_fallback_writes_title_to_stderr(self):
        screen, _ = make_screen()
        screen._active = False
        with patch("sys.stderr") as mock_err, patch("builtins.input", return_value="q"):
            screen.show_error_dialog("MyTitle", "the message", [("q", "Quit")])
        written = "".join(call.args[0] for call in mock_err.write.call_args_list)
        self.assertIn("MyTitle", written)

    def test_fallback_uses_last_option_when_input_empty(self):
        screen, _ = make_screen()
        screen._active = False
        with patch("sys.stderr"), patch("builtins.input", return_value=""):
            result = screen.show_error_dialog("Title", "msg", [("r", "Retry"), ("q", "Quit")])
        self.assertEqual(result, "q")


if __name__ == "__main__":
    unittest.main()
