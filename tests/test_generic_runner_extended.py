"""Extended unit tests for GenericRunner — covers previously untested branches."""

import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from agent_coordinator.infrastructure.generic_runner import GenericRunner
from agent_coordinator.infrastructure.pty_utils import PtyResult


def _make_pty_result(stdout="", stderr="", returncode=0):
    return PtyResult(returncode, stdout, stderr)


def _runner(config_extra=None, verbose=False):
    base = {"command": ["my-tool", "run"]}
    if config_extra:
        base.update(config_extra)
    return GenericRunner(base, verbose=verbose)


class TestVerbosePrintInRun(unittest.TestCase):
    """Lines 75-77: verbose label printed before invoking the tool."""

    def _run_verbose(self, session_id=None):
        runner = GenericRunner({"command": ["cool-cli"]}, verbose=True)
        pty = _make_pty_result(stdout="output")
        captured = StringIO()
        with patch(
            "agent_coordinator.infrastructure.generic_runner.run_with_pty",
            return_value=pty,
        ), patch("sys.stdout", captured):
            runner.run("msg", Path("/ws"), session_id=session_id)
        return captured.getvalue()

    def test_verbose_run_prints_tool_name(self):
        output = self._run_verbose()
        self.assertIn("cool-cli", output)

    def test_verbose_run_new_session_label(self):
        output = self._run_verbose(session_id=None)
        self.assertIn("new session", output)

    def test_verbose_run_existing_session_label(self):
        output = self._run_verbose(session_id="abc123def456xyz")
        self.assertIn("abc123def456", output)


class TestParseJsonViaRunWithPty(unittest.TestCase):
    """Line 116 + JSON path via run_with_pty patch."""

    def test_json_format_via_run_with_pty(self):
        pty = _make_pty_result(stdout='{"result": "hello", "session_id": "s1"}')
        runner = _runner({"output_format": "json", "json_text_field": "result", "json_session_field": "session_id"})
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty):
            result = runner.run("msg", Path("/ws"))
        self.assertEqual(result.text, "hello")
        self.assertEqual(result.session_id, "s1")

    def test_json_format_verbose_prints_text(self):
        pty = _make_pty_result(stdout='{"result": "verbose output"}')
        runner = GenericRunner({"command": ["t"], "output_format": "json"}, verbose=True)
        captured = StringIO()
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty), \
             patch("sys.stdout", captured):
            runner.run("msg", Path("/ws"))
        self.assertIn("verbose output", captured.getvalue())

    def test_json_invalid_falls_back_to_stdout(self):
        """JSONDecodeError path (line 200): raw stdout used as text."""
        pty = _make_pty_result(stdout="not-json-at-all")
        runner = _runner({"output_format": "json"})
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty):
            result = runner.run("msg", Path("/ws"))
        self.assertEqual(result.text, "not-json-at-all")

    def test_json_invalid_verbose_prints_fallback(self):
        """JSONDecodeError verbose path: stdout printed."""
        pty = _make_pty_result(stdout="raw fallback text")
        runner = GenericRunner({"command": ["t"], "output_format": "json"}, verbose=True)
        captured = StringIO()
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty), \
             patch("sys.stdout", captured):
            runner.run("msg", Path("/ws"))
        self.assertIn("raw fallback text", captured.getvalue())

    def test_json_error_nonzero_with_no_text_raises(self):
        pty = _make_pty_result(stdout='{"result": ""}', stderr="oops", returncode=1)
        runner = _runner({"output_format": "json"})
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty):
            with self.assertRaises(RuntimeError) as ctx:
                runner.run("msg", Path("/ws"))
        self.assertIn("exited 1", str(ctx.exception))


class TestParseJsonlDirectTextField(unittest.TestCase):
    """Lines 155-158: text_field directly in event (not nested in 'part')."""

    def test_direct_text_field_extracted(self):
        stdout = '{"text": "chunk A"}\n{"text": " chunk B"}\n'
        pty = _make_pty_result(stdout=stdout)
        runner = _runner({"output_format": "jsonl", "json_text_field": "text"})
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty):
            result = runner.run("msg", Path("/ws"))
        self.assertEqual(result.text, "chunk A chunk B")

    def test_direct_text_field_verbose_prints_chunks(self):
        """Lines 158+161: verbose print for direct text field."""
        stdout = '{"text": "verbose chunk"}\n'
        pty = _make_pty_result(stdout=stdout)
        runner = GenericRunner(
            {"command": ["t"], "output_format": "jsonl", "json_text_field": "text"},
            verbose=True,
        )
        captured = StringIO()
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty), \
             patch("sys.stdout", captured):
            runner.run("msg", Path("/ws"))
        self.assertIn("verbose chunk", captured.getvalue())

    def test_part_nested_text_field_verbose(self):
        """Lines 163-165, 168, 171: part.text field + verbose."""
        stdout = '{"part": {"text": "nested chunk"}}\n'
        pty = _make_pty_result(stdout=stdout)
        runner = GenericRunner(
            {"command": ["t"], "output_format": "jsonl", "json_text_field": "text"},
            verbose=True,
        )
        captured = StringIO()
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty), \
             patch("sys.stdout", captured):
            result = runner.run("msg", Path("/ws"))
        self.assertIn("nested chunk", captured.getvalue())
        self.assertEqual(result.text, "nested chunk")

    def test_session_id_extracted_from_jsonl(self):
        stdout = '{"sessionID": "sid-xyz"}\n{"text": "hi"}\n'
        pty = _make_pty_result(stdout=stdout)
        runner = _runner({"output_format": "jsonl", "json_text_field": "text", "json_session_field": "sessionID"})
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty):
            result = runner.run("msg", Path("/ws"))
        self.assertEqual(result.session_id, "sid-xyz")

    def test_jsonl_error_nonzero_no_text_raises(self):
        """Line 171 RuntimeError in _parse_jsonl."""
        pty = _make_pty_result(stdout="", stderr="something failed", returncode=2)
        runner = _runner({"output_format": "jsonl"})
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty):
            with self.assertRaises(RuntimeError) as ctx:
                runner.run("msg", Path("/ws"))
        self.assertIn("exited 2", str(ctx.exception))

    def test_jsonl_malformed_lines_skipped(self):
        stdout = "not-json\n{bad}\n{\"text\": \"ok\"}\n"
        pty = _make_pty_result(stdout=stdout)
        runner = _runner({"output_format": "jsonl", "json_text_field": "text"})
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty):
            result = runner.run("msg", Path("/ws"))
        self.assertEqual(result.text, "ok")


class TestParseTextViaRunWithPty(unittest.TestCase):
    """Line 215: error returncode path in _parse_text."""

    def test_text_format_nonzero_no_output_raises(self):
        pty = _make_pty_result(stdout="", stderr="died", returncode=1)
        runner = _runner({"output_format": "text"})
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty):
            with self.assertRaises(RuntimeError) as ctx:
                runner.run("msg", Path("/ws"))
        self.assertIn("exited 1", str(ctx.exception))

    def test_text_format_nonzero_with_output_does_not_raise(self):
        pty = _make_pty_result(stdout="some output", stderr="", returncode=1)
        runner = _runner({"output_format": "text"})
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty):
            result = runner.run("msg", Path("/ws"))
        self.assertEqual(result.text, "some output")

    def test_text_format_verbose_prints_output(self):
        pty = _make_pty_result(stdout="plain text result")
        runner = GenericRunner({"command": ["t"], "output_format": "text"}, verbose=True)
        captured = StringIO()
        with patch("agent_coordinator.infrastructure.generic_runner.run_with_pty", return_value=pty), \
             patch("sys.stdout", captured):
            runner.run("msg", Path("/ws"))
        self.assertIn("plain text result", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
