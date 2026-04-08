"""Unit tests for CopilotRunner."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_coordinator.infrastructure.copilot_runner import CopilotRunner
from agent_coordinator.infrastructure.pty_utils import PtyResult


class TestCopilotRunnerBuildCmd(unittest.TestCase):
    def setUp(self):
        self.runner = CopilotRunner()
        self.workspace = Path("/tmp/ws")

    def test_build_cmd_minimal(self):
        cmd = self.runner._build_cmd("hello", self.workspace, None, None)
        self.assertEqual(cmd, ["copilot", "--prompt", "hello", "--allow-all", "--no-color"])

    def test_build_cmd_with_session_id(self):
        cmd = self.runner._build_cmd("hello", self.workspace, "abc-uuid", None)
        self.assertIn("--resume", cmd)
        self.assertIn("abc-uuid", cmd)

    def test_build_cmd_with_model(self):
        cmd = self.runner._build_cmd("hello", self.workspace, None, "claude-opus-4.6")
        self.assertIn("--model", cmd)
        self.assertIn("claude-opus-4.6", cmd)


class TestCopilotRunnerExtractSessionId(unittest.TestCase):
    def setUp(self):
        self.runner = CopilotRunner()

    def test_extract_from_stderr(self):
        stderr = "session: aabbccdd-1234-5678-abcd-eeff00112233"
        result = self.runner._extract_session_id(stderr, None, "")
        self.assertEqual(result, "aabbccdd-1234-5678-abcd-eeff00112233")

    def test_extract_fallback_valid_uuid(self):
        fallback = "11111111-2222-3333-4444-555555555555"
        result = self.runner._extract_session_id("", fallback, "")
        self.assertEqual(result, fallback)

    def test_extract_fallback_non_uuid(self):
        result = self.runner._extract_session_id("", "not-a-uuid", "")
        self.assertEqual(result, "")


class TestCopilotRunnerRun(unittest.TestCase):
    def setUp(self):
        self.runner = CopilotRunner()
        self.workspace = Path("/fake/workspace")

    @patch("agent_coordinator.infrastructure.copilot_runner.run_with_pty")
    def test_run_success(self, mock_run_with_pty):
        mock_run_with_pty.return_value = PtyResult(
            0,
            "agent output",
            "session: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )
        result = self.runner.run("do something", self.workspace)
        self.assertEqual(result.text, "agent output")
        self.assertEqual(result.session_id, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    @patch("agent_coordinator.infrastructure.copilot_runner.run_with_pty")
    def test_run_failure_raises(self, mock_run_with_pty):
        mock_run_with_pty.return_value = PtyResult(1, "", "fatal error")
        with self.assertRaises(RuntimeError) as ctx:
            self.runner.run("do something", self.workspace)
        self.assertIn("copilot exited 1", str(ctx.exception))

    @patch("agent_coordinator.infrastructure.copilot_runner.run_with_pty")
    def test_run_passes_on_output(self, mock_run_with_pty):
        mock_run_with_pty.return_value = PtyResult(0, "out", "")
        cb = MagicMock()
        self.runner.run("do something", self.workspace, on_output=cb)
        _, kwargs = mock_run_with_pty.call_args
        self.assertIs(kwargs.get("on_output"), cb)


if __name__ == "__main__":
    unittest.main()
