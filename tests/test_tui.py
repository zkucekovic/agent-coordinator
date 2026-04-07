"""Unit tests for agent_coordinator/infrastructure/tui.py"""
import io
import sys
import unittest

from agent_coordinator.infrastructure.tui import (
    AgentState,
    InterruptMenu,
    Screen,
    SimpleProgressDisplay,
    Theme,
    _classify_error,
    _strip_ansi,
    _wrap_text,
    get_theme,
)


class TestGetTheme(unittest.TestCase):
    _REQUIRED_FIELDS = (
        "bg_header", "bg_status", "bg_separator",
        "led_running", "led_error", "led_blocked",
        "text_primary", "text_secondary", "text_dim",
        "color_agent", "color_success", "color_warning",
    )

    def _assert_theme(self, theme: Theme) -> None:
        self.assertIsInstance(theme, Theme)
        for field in self._REQUIRED_FIELDS:
            self.assertTrue(hasattr(theme, field), f"Theme missing field: {field}")

    def test_none_returns_theme_with_all_fields(self):
        self._assert_theme(get_theme(None))

    def test_catppuccin_frappe_returns_theme_with_all_fields(self):
        self._assert_theme(get_theme("catppuccin-frappe"))

    def test_dark_returns_theme(self):
        self._assert_theme(get_theme("dark"))

    def test_nonexistent_returns_catppuccin_frappe(self):
        theme = get_theme("nonexistent")
        self._assert_theme(theme)
        self.assertEqual(theme.name, "catppuccin-frappe")


class TestStripAnsi(unittest.TestCase):
    def test_strips_bold_escape(self):
        self.assertEqual(_strip_ansi("\033[1mHello\033[0m world"), "Hello world")

    def test_no_escapes_unchanged(self):
        self.assertEqual(_strip_ansi("no escapes"), "no escapes")

    def test_strips_truecolor_escape(self):
        self.assertEqual(_strip_ansi("\033[38;2;100;200;50mcolour\033[0m"), "colour")


class TestWrapText(unittest.TestCase):
    def test_wraps_at_width(self):
        result = _wrap_text("hello world foo", 8)
        self.assertIsInstance(result, list)
        for line in result:
            self.assertLessEqual(len(line), 8, f"Line too long: {line!r}")

    def test_preserves_newlines(self):
        result = _wrap_text("line1\nline2", 80)
        self.assertEqual(len(result), 2)


class TestClassifyError(unittest.TestCase):
    def test_model_not_available(self):
        title, _ = _classify_error(RuntimeError('Model "foo" from --model flag is not available.'))
        self.assertIn("Model", title)

    def test_stale_session(self):
        title, _ = _classify_error(RuntimeError("No session or task matched 'abc'"))
        self.assertIn("Stale", title)

    def test_backend_error(self):
        title, _ = _classify_error(RuntimeError("copilot exited 1: some error"))
        self.assertIn("Backend", title)

    def test_handoff_parse_error(self):
        title, _ = _classify_error(RuntimeError("No valid handoff block"))
        self.assertIn("Handoff", title)

    def test_unknown_agent(self):
        title, _ = _classify_error(RuntimeError("Unknown agent 'x'"))
        self.assertIn("Config", title)

    def test_generic_fallback(self):
        title, _ = _classify_error(ValueError("something random"))
        self.assertEqual(title, "ValueError")


class TestScreen(unittest.TestCase):
    def _make_screen(self) -> Screen:
        stream = io.StringIO()
        # Patch isatty so Screen doesn't attempt TTY operations
        stream.isatty = lambda: False  # type: ignore[method-assign]
        return Screen(stream=stream)

    def test_init_without_tty(self):
        screen = self._make_screen()
        self.assertIsInstance(screen, Screen)

    def test_set_paused_true(self):
        screen = self._make_screen()
        screen.set_paused(True)
        self.assertTrue(screen._paused)

    def test_set_paused_false(self):
        screen = self._make_screen()
        screen._paused = True
        screen.set_paused(False)
        self.assertFalse(screen._paused)

    def test_close_when_inactive_is_noop(self):
        screen = self._make_screen()
        self.assertFalse(screen._active)
        # Should not raise
        screen.close()

    def test_append_content_adds_to_lines(self):
        screen = self._make_screen()
        screen._append_content("line")
        self.assertIn("line", screen._lines)


class TestSimpleProgressDisplay(unittest.TestCase):
    def _make(self) -> SimpleProgressDisplay:
        return SimpleProgressDisplay(stream=io.StringIO())

    def test_start_run(self):
        d = self._make()
        d.start_run(["a", "b"], "/workspace", 10)

    def test_start_agent_turn(self):
        d = self._make()
        d.start_agent_turn("agent1", "copilot", "task-1", "in_progress")

    def test_update_output(self):
        d = self._make()
        d.update_output("some output\n")

    def test_finish_agent_turn(self):
        d = self._make()
        d.finish_agent_turn(True, "done", "agent2")

    def test_close(self):
        d = self._make()
        d.close()


class TestInterruptMenu(unittest.TestCase):
    def test_instantiates_with_none(self):
        menu = InterruptMenu(None)
        self.assertIsInstance(menu, InterruptMenu)


class TestAgentState(unittest.TestCase):
    def test_all_states_exist(self):
        self.assertTrue(hasattr(AgentState, "RUNNING"))
        self.assertTrue(hasattr(AgentState, "IDLE"))
        self.assertTrue(hasattr(AgentState, "ERROR"))
        self.assertTrue(hasattr(AgentState, "DONE"))
        self.assertTrue(hasattr(AgentState, "BLOCKED"))


if __name__ == "__main__":
    unittest.main()
