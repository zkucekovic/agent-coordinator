"""Unit tests for agent_coordinator/infrastructure/pty_utils.py"""

import unittest
from pathlib import Path

from agent_coordinator.infrastructure.pty_utils import (
    PtyResult,
    _run_pipe,
    _strip,
    run_with_pty,
)


class TestStrip(unittest.TestCase):
    def test_plain_text_unchanged(self):
        self.assertEqual(_strip("hello"), "hello")

    def test_strips_bold_escape(self):
        self.assertEqual(_strip("\033[1mBold\033[0m"), "Bold")


class TestPtyResult(unittest.TestCase):
    def test_attributes(self):
        result = PtyResult(0, "out", "err")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "out")
        self.assertEqual(result.stderr, "err")


class TestRunWithPty(unittest.TestCase):
    def test_run_with_pty_echo(self):
        # In pytest stdin is not a TTY, so run_with_pty takes the _run_pipe path.
        result = run_with_pty(["echo", "hello"], cwd=Path("/tmp"))
        self.assertIn("hello", result.stdout)


class TestRunPipe(unittest.TestCase):
    def test_echo_returns_output(self):
        result = _run_pipe(["echo", "hello world"], cwd=Path("/tmp"), env=None, on_output=None)
        self.assertIn("hello world", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_with_on_output_callback(self):
        collected: list[str] = []
        result = _run_pipe(
            ["echo", "streaming"],
            cwd=Path("/tmp"),
            env=None,
            on_output=collected.append,
        )
        self.assertEqual(result.returncode, 0)
        joined = "".join(collected)
        self.assertIn("streaming", joined)

    def test_false_returns_nonzero(self):
        result = _run_pipe(["false"], cwd=Path("/tmp"), env=None, on_output=None)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
