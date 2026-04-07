"""Unit tests for OpenCodeRunner."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent_coordinator.infrastructure.opencode_runner import OpenCodeRunner
from agent_coordinator.infrastructure.pty_utils import PtyResult


class TestOpenCodeRunnerBuildCmd(unittest.TestCase):
    def setUp(self):
        self.runner = OpenCodeRunner()
        self.workspace = Path("/fake/workspace")

    def test_build_cmd_no_session(self):
        cmd = self.runner._build_cmd("hello", self.workspace, None, None)
        self.assertEqual(
            cmd,
            ["opencode", "run", "hello", "--format", "json", "--dir", str(self.workspace)],
        )

    def test_build_cmd_with_session_id(self):
        cmd = self.runner._build_cmd("hello", self.workspace, "sess-abc", None)
        self.assertIn("--continue", cmd)
        self.assertIn("--session", cmd)
        self.assertIn("sess-abc", cmd)


class TestOpenCodeRunnerParseLines(unittest.TestCase):
    def setUp(self):
        self.runner = OpenCodeRunner()

    def test_parse_text_event(self):
        lines = [json.dumps({"type": "text", "part": {"text": "hello"}})]
        result = self.runner._parse_lines(lines, None, None)
        self.assertEqual(result.text, "hello")

    def test_parse_session_id_from_event(self):
        lines = [json.dumps({"sessionID": "abc"})]
        result = self.runner._parse_lines(lines, None, None)
        self.assertEqual(result.session_id, "abc")

    def test_parse_error_event_no_text_raises(self):
        lines = [json.dumps({"type": "error"})]
        with self.assertRaises(RuntimeError):
            self.runner._parse_lines(lines, None, None)


class TestOpenCodeRunnerRun(unittest.TestCase):
    def setUp(self):
        self.runner = OpenCodeRunner()
        self.workspace = Path("/fake/workspace")

    @patch("agent_coordinator.infrastructure.opencode_runner.run_with_pty")
    def test_run_capture_collects_lines(self, mock_run_with_pty):
        text_line = json.dumps({"type": "text", "part": {"text": "result text"}})

        def fake_run_with_pty(cmd, cwd, on_output=None):
            if on_output:
                on_output(text_line)
            return PtyResult(0, "", "")

        mock_run_with_pty.side_effect = fake_run_with_pty

        result = self.runner.run("do something", self.workspace)
        self.assertEqual(result.text, "result text")
        mock_run_with_pty.assert_called_once()


if __name__ == "__main__":
    unittest.main()
