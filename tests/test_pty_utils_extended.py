"""Extended tests for agent_coordinator/infrastructure/pty_utils.py.

The existing tests/test_pty_utils.py covers basic _strip, PtyResult attributes,
and the _run_pipe path.  This file adds wider coverage.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_coordinator.infrastructure.pty_utils import (
    PtyResult,
    _run_pipe,
    _strip,
    run_with_pty,
)


# ── _strip: comprehensive ANSI stripping ──────────────────────────────────────

class TestStrip:
    def test_plain_text_unchanged(self):
        assert _strip("hello world") == "hello world"

    def test_bold_and_reset(self):
        assert _strip("\033[1mBold\033[0m") == "Bold"

    def test_256_colour_foreground(self):
        assert _strip("\033[38;5;200mtext\033[0m") == "text"

    def test_cursor_movement_stripped(self):
        # CSI A (cursor up)
        assert _strip("\033[2Ahello") == "hello"

    def test_osc_sequence_stripped(self):
        # OSC sets window title: ESC ] ... BEL
        assert _strip("\033]0;Window Title\x07plain") == "plain"

    def test_character_set_designation_stripped(self):
        # ESC ( B  →  designate G0 character set
        assert _strip("\033(Btext") == "text"

    def test_two_char_esc_sequence_stripped(self):
        # ESC M  (reverse index)
        assert _strip("\033Mtext") == "text"

    def test_multiple_sequences(self):
        raw = "\033[1m\033[32mGreen Bold\033[0m and \033[31mRed\033[0m"
        assert _strip(raw) == "Green Bold and Red"

    def test_empty_string(self):
        assert _strip("") == ""

    def test_newlines_preserved(self):
        assert _strip("line1\nline2") == "line1\nline2"

    def test_no_false_positive_on_backslash(self):
        assert _strip("path\\to\\file") == "path\\to\\file"


# ── PtyResult ─────────────────────────────────────────────────────────────────

class TestPtyResult:
    def test_constructor_stores_fields(self):
        r = PtyResult(returncode=0, stdout="out", stderr="err")
        assert r.returncode == 0
        assert r.stdout == "out"
        assert r.stderr == "err"

    def test_nonzero_returncode(self):
        r = PtyResult(returncode=1, stdout="", stderr="oops")
        assert r.returncode == 1

    def test_slots_prevent_arbitrary_attributes(self):
        r = PtyResult(0, "", "")
        with pytest.raises(AttributeError):
            r.unexpected = "x"  # type: ignore[attr-defined]

    def test_empty_strings(self):
        r = PtyResult(0, "", "")
        assert r.stdout == ""
        assert r.stderr == ""

    def test_multiline_stdout(self):
        r = PtyResult(0, "line1\nline2", "")
        assert "line1" in r.stdout
        assert "line2" in r.stdout


# ── _run_pipe: extended coverage ──────────────────────────────────────────────

class TestRunPipeExtended:
    def test_cwd_passed_to_subprocess(self, tmp_path):
        result = _run_pipe(["pwd"], cwd=tmp_path, env=None, on_output=None)
        assert result.returncode == 0
        assert str(tmp_path) in result.stdout

    def test_env_is_forwarded(self, tmp_path):
        import os
        env = {**os.environ, "MY_TEST_VAR": "hello_env"}
        result = _run_pipe(
            ["env"],
            cwd=tmp_path,
            env=env,
            on_output=None,
        )
        assert "MY_TEST_VAR=hello_env" in result.stdout

    def test_stderr_is_captured(self, tmp_path):
        result = _run_pipe(
            ["sh", "-c", "echo error_text >&2"],
            cwd=tmp_path,
            env=None,
            on_output=None,
        )
        assert "error_text" in result.stderr

    def test_on_output_streams_lines(self, tmp_path):
        collected: list[str] = []
        _run_pipe(
            ["printf", "a\nb\nc\n"],
            cwd=tmp_path,
            env=None,
            on_output=collected.append,
        )
        joined = "".join(collected)
        assert "a" in joined
        assert "b" in joined
        assert "c" in joined

    def test_on_output_stderr_captured_separately(self, tmp_path):
        stderr_lines: list[str] = []
        result = _run_pipe(
            ["sh", "-c", "echo stdout_line; echo stderr_line >&2"],
            cwd=tmp_path,
            env=None,
            on_output=lambda l: None,
        )
        assert "stderr_line" in result.stderr

    def test_nonzero_returncode_pipe(self, tmp_path):
        result = _run_pipe(
            ["sh", "-c", "exit 42"],
            cwd=tmp_path,
            env=None,
            on_output=None,
        )
        assert result.returncode == 42

    def test_stdout_stripped_of_trailing_whitespace(self, tmp_path):
        result = _run_pipe(
            ["printf", "  hello  \n"],
            cwd=tmp_path,
            env=None,
            on_output=None,
        )
        assert result.stdout == "hello"

    def test_on_output_receives_each_line(self, tmp_path):
        lines: list[str] = []
        _run_pipe(
            ["sh", "-c", "echo first; echo second"],
            cwd=tmp_path,
            env=None,
            on_output=lines.append,
        )
        assert any("first" in l for l in lines)
        assert any("second" in l for l in lines)


# ── run_with_pty: pipe fallback ───────────────────────────────────────────────

class TestRunWithPty:
    def test_pipe_path_used_when_stdin_not_tty(self):
        """In test environment stdin is not a TTY, so _run_pipe is used."""
        result = run_with_pty(["echo", "hello"], cwd=Path("/tmp"))
        assert "hello" in result.stdout
        assert result.returncode == 0

    def test_pipe_path_used_when_has_pty_false(self):
        """Explicitly simulate a platform without pty."""
        import agent_coordinator.infrastructure.pty_utils as pu
        with patch.object(pu, "_HAS_PTY", False):
            result = run_with_pty(["echo", "no-pty"])
        assert "no-pty" in result.stdout

    def test_on_output_callback_via_run_with_pty(self):
        collected: list[str] = []
        run_with_pty(
            ["echo", "streamed"],
            on_output=collected.append,
        )
        assert any("streamed" in l for l in collected)


# ── PTY path: skipped (requires real TTY) ─────────────────────────────────────

@pytest.mark.skipif(True, reason="requires real TTY - integration test only")
def test_pty_path_requires_tty():
    pass
