"""Unit tests for agent_coordinator/infrastructure/pty_utils.py"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

import agent_coordinator.infrastructure.pty_utils as pty_utils
from agent_coordinator.infrastructure.pty_utils import (
    PtyResult,
    _run_pty,
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

    def test_run_pty_cleans_up_before_reraising_keyboard_interrupt(self):
        master_fd, slave_fd = os.pipe()
        stderr_r, stderr_w = os.pipe()
        self.addCleanup(lambda: [os.close(fd) for fd in (master_fd, slave_fd, stderr_r, stderr_w) if self._is_open(fd)])

        joined: list[tuple[str | None, float | None]] = []
        closed: list[int] = []
        real_close = os.close

        class FakeThread:
            def __init__(self, *, name=None, **_kwargs):
                self.name = name

            def start(self):
                return None

            def join(self, timeout=None):
                joined.append((self.name, timeout))

        class FakeProc:
            def __init__(self):
                self.returncode = -15
                self.terminate_calls = 0
                self.kill_calls = 0
                self.wait_calls: list[float | None] = []
                self._first_wait = True

            def wait(self, timeout=None):
                self.wait_calls.append(timeout)
                if self._first_wait and timeout is None:
                    self._first_wait = False
                    raise KeyboardInterrupt
                return self.returncode

            def terminate(self):
                self.terminate_calls += 1

            def kill(self):
                self.kill_calls += 1

        proc = FakeProc()

        def tracking_close(fd: int) -> None:
            closed.append(fd)
            real_close(fd)

        with (
            patch.object(pty_utils, "_setup_pty", return_value=(master_fd, slave_fd, stderr_r, stderr_w)),
            patch.object(pty_utils, "_drain_stderr", return_value=b""),
            patch.object(pty_utils.threading, "Thread", FakeThread),
            patch("subprocess.Popen", return_value=proc),
            patch("agent_coordinator.infrastructure.pty_utils.os.close", side_effect=tracking_close),
        ):
            with self.assertRaises(KeyboardInterrupt):
                _run_pty(["echo", "hello"], cwd=None, env=None, on_output=None)

        self.assertEqual(proc.terminate_calls, 1)
        self.assertEqual(proc.kill_calls, 0)
        self.assertEqual(proc.wait_calls, [None, 0.1])
        self.assertIn(("pty-out", 2), joined)
        self.assertIn(("pty-in", 0.5), joined)
        self.assertEqual(closed, [slave_fd, stderr_w, master_fd, stderr_r])

    @staticmethod
    def _is_open(fd: int) -> bool:
        try:
            os.fstat(fd)
        except OSError:
            return False
        return True


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
