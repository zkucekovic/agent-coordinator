"""Unit tests for startup_cli.py — Command, COMMANDS, and StartupCLI."""

import unittest
from unittest.mock import MagicMock

from agent_coordinator.infrastructure.startup_cli import COMMANDS, Command, StartupCLI


def make_mock_screen():
    screen = MagicMock()
    screen._theme.color_success = ""
    screen._theme.color_warning = ""
    screen._theme.color_agent = ""
    screen._theme.text_dim = ""
    screen._theme.text_secondary = ""
    screen._theme.text_primary = ""
    screen._theme.led_error = ""
    screen._cols = 80
    screen._rows = 24
    screen._active = False
    screen._append_content = MagicMock()
    screen.read_input = MagicMock(return_value="")
    screen.start_menu = MagicMock()
    return screen


class TestCommand(unittest.TestCase):
    def test_matches_with_slash_prefix(self):
        cmd = Command("foo", "desc")
        self.assertTrue(cmd.matches("/foo"))

    def test_matches_without_slash(self):
        cmd = Command("foo", "desc")
        self.assertTrue(cmd.matches("foo"))

    def test_matches_alias(self):
        cmd = Command("foo", "desc", aliases=["f"])
        self.assertTrue(cmd.matches("f"))

    def test_no_match_wrong_token(self):
        cmd = Command("foo", "desc")
        self.assertFalse(cmd.matches("bar"))

    def test_case_insensitive(self):
        cmd = Command("foo", "desc")
        self.assertTrue(cmd.matches("FOO"))
        self.assertTrue(cmd.matches("/FOO"))


class TestCommandsRegistry(unittest.TestCase):
    def test_all_commands_have_non_empty_name(self):
        for cmd in COMMANDS:
            with self.subTest(cmd=cmd.name):
                self.assertTrue(cmd.name.strip())

    def test_all_commands_have_non_empty_description(self):
        for cmd in COMMANDS:
            with self.subTest(cmd=cmd.name):
                self.assertTrue(cmd.description.strip())

    def test_commands_include_expected_names(self):
        names = {c.name for c in COMMANDS}
        for expected in ("init", "run", "status", "help", "quit"):
            self.assertIn(expected, names)


class TestStartupCLIInstantiation(unittest.TestCase):
    def test_instantiates_without_error(self):
        screen = make_mock_screen()
        cli = StartupCLI(screen=screen)
        self.assertIsNotNone(cli)

    def test_stores_screen(self):
        screen = make_mock_screen()
        cli = StartupCLI(screen=screen)
        self.assertIs(cli._screen, screen)


class TestStartupCLIDispatch(unittest.TestCase):
    def setUp(self):
        self.screen = make_mock_screen()
        self.cli = StartupCLI(screen=self.screen)

    def test_dispatch_help_returns_none(self):
        result = self.cli._dispatch("/help")
        self.assertIsNone(result)

    def test_dispatch_help_calls_render_menu(self):
        self.cli._dispatch("/help")
        self.screen._append_content.assert_called()

    def test_dispatch_quit_returns_action_quit(self):
        result = self.cli._dispatch("/quit")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "quit")

    def test_dispatch_unknown_returns_none(self):
        result = self.cli._dispatch("/unknown_xyz")
        self.assertIsNone(result)

    def test_dispatch_unknown_appends_warning(self):
        self.cli._dispatch("/unknown_xyz")
        self.screen._append_content.assert_called()
        call_args = self.screen._append_content.call_args_list
        warning_shown = any("Unknown command" in str(call) or "unknown_xyz" in str(call) for call in call_args)
        self.assertTrue(warning_shown)

    def test_dispatch_alias_q(self):
        result = self.cli._dispatch("q")
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "quit")


class TestStartupCLICommandHandlers(unittest.TestCase):
    def setUp(self):
        self.screen = make_mock_screen()
        self.cli = StartupCLI(screen=self.screen)

    def test_cmd_quit_returns_action_quit(self):
        result = self.cli._cmd_quit([])
        self.assertEqual(result, {"action": "quit"})

    def test_cmd_init_with_path_arg(self):
        result = self.cli._cmd_init(["./testpath"])
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "init")
        self.assertIn("testpath", str(result["workspace"]))

    def test_cmd_init_with_empty_input_returns_none(self):
        self.screen.read_input.return_value = ""
        result = self.cli._cmd_init([])
        self.assertIsNone(result)

    def test_cmd_init_prompts_when_no_args(self):
        self.screen.read_input.return_value = "./myworkspace"
        result = self.cli._cmd_init([])
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "init")
        self.assertIn("myworkspace", str(result["workspace"]))

    def test_cmd_run_with_path_arg(self):
        result = self.cli._cmd_run(["./ws"])
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "run")
        self.assertIn("ws", str(result["workspace"]))

    def test_cmd_run_no_args_empty_input_returns_none(self):
        self.screen.read_input.return_value = ""
        result = self.cli._cmd_run([])
        self.assertIsNone(result)

    def test_cmd_status_nonexistent_workspace_calls_warn(self):
        result = self.cli._cmd_status(["/nonexistent/path/abc123xyz"])
        self.assertIsNone(result)
        # _warn appends content with "⚠"
        calls = [str(c) for c in self.screen._append_content.call_args_list]
        self.assertTrue(any("not found" in c.lower() or "⚠" in c for c in calls))

    def test_cmd_status_prompts_when_no_args(self):
        self.screen.read_input.return_value = "/nonexistent/path/abc123xyz"
        result = self.cli._cmd_status([])
        self.assertIsNone(result)
        self.screen.read_input.assert_called()


if __name__ == "__main__":
    unittest.main()
