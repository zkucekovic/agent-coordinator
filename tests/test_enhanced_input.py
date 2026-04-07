"""Tests for agent_coordinator/infrastructure/enhanced_input.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

import agent_coordinator.infrastructure.enhanced_input as ei_module
from agent_coordinator.infrastructure.enhanced_input import (
    Colors,
    EnhancedInput,
    enhanced_choice,
    enhanced_input,
    enhanced_multiline,
    get_input,
)


# ── EnhancedInput.__init__ & _setup_readline ──────────────────────────────────

class TestEnhancedInputInit:
    def test_default_no_history_file(self):
        obj = EnhancedInput()
        assert obj.history_file is None

    def test_stores_history_file(self, tmp_path):
        hf = tmp_path / "hist"
        obj = EnhancedInput(history_file=hf)
        assert obj.history_file == hf

    def test_loads_existing_history_file(self, tmp_path):
        hf = tmp_path / "hist"
        hf.write_text("")  # create an empty but existing file
        # Should not raise; readline.read_history_file is called
        obj = EnhancedInput(history_file=hf)
        assert obj.history_file == hf

    def test_setup_readline_when_unavailable(self):
        with patch.object(ei_module, "READLINE_AVAILABLE", False):
            obj = EnhancedInput()
        # Should construct without error
        assert obj is not None

    def test_history_file_read_exception_is_swallowed(self, tmp_path):
        hf = tmp_path / "hist"
        hf.write_text("")
        with patch("readline.read_history_file", side_effect=OSError("bad")):
            obj = EnhancedInput(history_file=hf)
        assert obj is not None


# ── save_history ──────────────────────────────────────────────────────────────

class TestSaveHistory:
    def test_save_history_no_file_does_nothing(self):
        obj = EnhancedInput()
        obj.save_history()  # Should not raise

    def test_save_history_creates_file(self, tmp_path):
        hf = tmp_path / "subdir" / "hist"
        obj = EnhancedInput(history_file=hf)
        obj.save_history()
        assert hf.exists()

    def test_save_history_when_readline_unavailable(self, tmp_path):
        hf = tmp_path / "hist"
        obj = EnhancedInput(history_file=hf)
        with patch.object(ei_module, "READLINE_AVAILABLE", False):
            obj.save_history()  # Should silently do nothing

    def test_save_history_write_exception_swallowed(self, tmp_path):
        hf = tmp_path / "hist"
        obj = EnhancedInput(history_file=hf)
        with patch("readline.write_history_file", side_effect=OSError("disk full")):
            obj.save_history()  # Should not raise


# ── EnhancedInput.input ───────────────────────────────────────────────────────

class TestEnhancedInputMethod:
    def test_basic_input_returns_user_text(self):
        with patch("builtins.input", return_value="hello"):
            obj = EnhancedInput()
            result = obj.input("prompt: ")
        assert result == "hello"

    def test_input_with_default_sets_pre_input_hook(self):
        hook_calls = []
        with patch("readline.set_pre_input_hook") as mock_hook:
            with patch("builtins.input", return_value="typed"):
                obj = EnhancedInput()
                result = obj.input("p: ", default="mydefault")
        # set_pre_input_hook called twice: once to set, once to clear (None)
        assert mock_hook.call_count == 2
        assert mock_hook.call_args_list[-1] == call(None)
        assert result == "typed"

    def test_input_without_default_does_not_set_hook(self):
        with patch("readline.set_pre_input_hook") as mock_hook:
            with patch("builtins.input", return_value="typed"):
                obj = EnhancedInput()
                obj.input("p: ")
        mock_hook.assert_not_called()

    def test_input_with_completer(self):
        my_completer = MagicMock(return_value=None)
        with patch("readline.set_completer") as mock_sc:
            with patch("builtins.input", return_value="done"):
                obj = EnhancedInput()
                result = obj.input("p: ", completer=my_completer)
        # set_completer called to set and then clear
        assert mock_sc.call_count == 2
        assert mock_sc.call_args_list[-1] == call(None)
        assert result == "done"

    def test_input_when_readline_unavailable_uses_builtin(self):
        with patch.object(ei_module, "READLINE_AVAILABLE", False):
            with patch("builtins.input", return_value="fallback") as mock_input:
                obj = EnhancedInput()
                result = obj.input("p: ")
        mock_input.assert_called_once_with("p: ")
        assert result == "fallback"

    def test_input_saves_history(self, tmp_path):
        hf = tmp_path / "hist"
        obj = EnhancedInput(history_file=hf)
        with patch("builtins.input", return_value="x"):
            obj.input("p: ")
        assert hf.exists()


# ── EnhancedInput.choice ──────────────────────────────────────────────────────

class TestChoiceMethod:
    def test_valid_choice_returned(self):
        with patch("builtins.input", return_value="yes"):
            obj = EnhancedInput()
            result = obj.choice("Pick: ", ["yes", "no"])
        assert result == "yes"

    def test_choice_strips_and_lowercases(self):
        with patch("builtins.input", return_value="  YES  "):
            obj = EnhancedInput()
            result = obj.choice("Pick: ", ["yes", "no"])
        assert result == "yes"

    def test_invalid_then_valid_choice(self, capsys):
        inputs = iter(["bad", "no"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            obj = EnhancedInput()
            result = obj.choice("Pick: ", ["yes", "no"])
        assert result == "no"
        out = capsys.readouterr().out
        assert "Invalid choice" in out

    def test_default_prefills_choice(self):
        with patch("readline.set_pre_input_hook") as mock_hook:
            with patch("builtins.input", return_value="yes"):
                obj = EnhancedInput()
                result = obj.choice("Pick: ", ["yes", "no"], default="yes")
        assert result == "yes"

    def test_completer_matches_prefix(self):
        """The inner completer function should return matching choices by prefix."""
        completions = []

        def capture_completer(completer_fn):
            # Only invoke when a real completer is passed (not the clear call with None)
            if completer_fn is None:
                return
            completions.extend([
                completer_fn("y", 0),
                completer_fn("y", 1),
                completer_fn("n", 0),
                completer_fn("z", 0),
            ])

        with patch("readline.set_completer", side_effect=capture_completer):
            with patch("readline.set_pre_input_hook"):
                with patch("builtins.input", return_value="yes"):
                    obj = EnhancedInput()
                    obj.choice("Pick: ", ["yes", "no"], default="yes")

        assert completions[0] == "yes"   # "y" state=0
        assert completions[1] is None    # "y" state=1 (only one match)
        assert completions[2] == "no"    # "n" state=0
        assert completions[3] is None    # "z" state=0 (no match)


# ── EnhancedInput.multiline ───────────────────────────────────────────────────

class TestMultilineMethod:
    def test_returns_lines_joined(self):
        inputs = iter(["line one", "line two", ""])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            obj = EnhancedInput()
            result = obj.multiline()
        assert result == "line one\nline two"

    def test_eof_error_breaks_loop(self):
        with patch("builtins.input", side_effect=EOFError):
            obj = EnhancedInput()
            result = obj.multiline()
        assert result == ""

    def test_keyboard_interrupt_breaks_loop(self):
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            obj = EnhancedInput()
            result = obj.multiline()
        assert result == ""

    def test_custom_prompts(self, capsys):
        with patch("builtins.input", return_value=""):
            obj = EnhancedInput()
            obj.multiline(prompt="Enter stuff:", line_prompt=">> ")
        out = capsys.readouterr().out
        assert "Enter stuff:" in out

    def test_no_prompt_skips_print(self, capsys):
        with patch("builtins.input", return_value=""):
            obj = EnhancedInput()
            obj.multiline(prompt="")
        out = capsys.readouterr().out
        assert out == ""


# ── Global get_input ──────────────────────────────────────────────────────────

class TestGetInput:
    def test_returns_enhanced_input_instance(self):
        # Reset global to ensure fresh creation
        ei_module._global_input = None
        result = get_input()
        assert isinstance(result, EnhancedInput)

    def test_returns_same_instance_on_second_call(self):
        ei_module._global_input = None
        first = get_input()
        second = get_input()
        assert first is second

    def teardown_method(self):
        # Clean up global state between tests
        ei_module._global_input = None


# ── Convenience functions ─────────────────────────────────────────────────────

class TestConvenienceFunctions:
    def setup_method(self):
        ei_module._global_input = None

    def teardown_method(self):
        ei_module._global_input = None

    def test_enhanced_input_returns_string(self):
        with patch("builtins.input", return_value="typed"):
            result = enhanced_input("p: ")
        assert result == "typed"

    def test_enhanced_input_with_default(self):
        with patch("readline.set_pre_input_hook"):
            with patch("builtins.input", return_value="typed"):
                result = enhanced_input("p: ", default="def")
        assert result == "typed"

    def test_enhanced_choice_returns_valid(self):
        with patch("builtins.input", return_value="a"):
            result = enhanced_choice("Pick: ", ["a", "b"])
        assert result == "a"

    def test_enhanced_multiline_returns_joined(self):
        inputs = iter(["hello", "world", ""])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            result = enhanced_multiline()
        assert result == "hello\nworld"


# ── Colors ────────────────────────────────────────────────────────────────────

class TestColors:
    def test_colorize_when_disabled_returns_text(self):
        with patch.object(Colors, "ENABLED", False):
            result = Colors.colorize("hello", "\033[31m")
        assert result == "hello"

    def test_colorize_when_enabled_wraps_text(self):
        with patch.object(Colors, "ENABLED", True):
            with patch.object(Colors, "RESET", "\033[0m"):
                result = Colors.colorize("hello", "\033[31m")
        assert result == "\033[31mhello\033[0m"

    def test_prompt_returns_string(self):
        result = Colors.prompt("my prompt")
        assert isinstance(result, str)

    def test_success_returns_string(self):
        result = Colors.success("ok")
        assert isinstance(result, str)

    def test_error_returns_string(self):
        result = Colors.error("fail")
        assert isinstance(result, str)

    def test_warning_returns_string(self):
        result = Colors.warning("warn")
        assert isinstance(result, str)

    def test_info_returns_string(self):
        result = Colors.info("info text")
        assert isinstance(result, str)

    def test_supports_color_false_when_not_tty(self):
        with patch.object(sys.stdout, "isatty", return_value=False):
            result = Colors._supports_color()
        assert result is False

    def test_supports_color_false_when_no_color_env(self, monkeypatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setenv("NO_COLOR", "1")
        result = Colors._supports_color()
        assert result is False

    def test_supports_color_false_when_dumb_term(self, monkeypatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        result = Colors._supports_color()
        assert result is False

    def test_supports_color_true_when_tty_and_no_overrides(self, monkeypatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        result = Colors._supports_color()
        assert result is True
