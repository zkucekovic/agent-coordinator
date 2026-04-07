"""Unit tests for ClaudeCodeRunner."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent_coordinator.infrastructure.claude_runner import ClaudeCodeRunner
from agent_coordinator.infrastructure.pty_utils import PtyResult


class TestClaudeRunnerBuildCmd(unittest.TestCase):
    def setUp(self):
        self.runner = ClaudeCodeRunner()
        self.workspace = Path("/fake/workspace")

    def test_build_cmd_no_session(self):
        cmd = self.runner._build_cmd("hello", self.workspace, None, None)
        self.assertEqual(
            cmd,
            ["claude", "--print", "--output-format", "json",
             "--permission-mode", "bypassPermissions",
             "--cwd", str(self.workspace), "hello"],
        )

    def test_build_cmd_with_session_id(self):
        cmd = self.runner._build_cmd("hello", self.workspace, "sess-123", None)
        self.assertIn("--continue", cmd)
        self.assertIn("--session-id", cmd)
        self.assertIn("sess-123", cmd)

    def test_build_cmd_with_model(self):
        cmd = self.runner._build_cmd("hello", self.workspace, None, "claude-opus-4.6")
        self.assertIn("--model", cmd)
        self.assertIn("claude-opus-4.6", cmd)


class TestClaudeRunnerParseOutput(unittest.TestCase):
    def setUp(self):
        self.runner = ClaudeCodeRunner()

    def test_parse_valid_json(self):
        result = PtyResult(0, json.dumps({"result": "text", "session_id": "abc"}), "")
        run_result = self.runner._parse_output(result, None)
        self.assertEqual(run_result.text, "text")
        self.assertEqual(run_result.session_id, "abc")

    def test_parse_non_json_stdout(self):
        stdout_value = "plain text output"
        result = PtyResult(0, stdout_value, "")
        run_result = self.runner._parse_output(result, None)
        self.assertEqual(run_result.text, stdout_value)

    def test_parse_error_no_text_raises(self):
        result = PtyResult(1, "", "something went wrong")
        with self.assertRaises(RuntimeError):
            self.runner._parse_output(result, None)


class TestClaudeRunnerRun(unittest.TestCase):
    def setUp(self):
        self.runner = ClaudeCodeRunner()
        self.workspace = Path("/fake/workspace")

    @patch("agent_coordinator.infrastructure.claude_runner.run_with_pty")
    def test_run_end_to_end(self, mock_run_with_pty):
        payload = json.dumps({"result": "done", "session_id": "sess-xyz"})
        mock_run_with_pty.return_value = PtyResult(0, payload, "")
        result = self.runner.run("do work", self.workspace)
        self.assertEqual(result.text, "done")
        self.assertEqual(result.session_id, "sess-xyz")
        mock_run_with_pty.assert_called_once()


if __name__ == "__main__":
    unittest.main()
