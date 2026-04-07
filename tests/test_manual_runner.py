"""Unit tests for ManualRunner — human-in-the-loop agent backend."""

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from agent_coordinator.domain.models import RunResult
from agent_coordinator.infrastructure.manual_runner import ManualRunner


class TestManualRunnerInstantiation(unittest.TestCase):
    def test_default_verbose_true(self):
        runner = ManualRunner()
        self.assertTrue(runner._verbose)

    def test_verbose_false(self):
        runner = ManualRunner(verbose=False)
        self.assertFalse(runner._verbose)

    def test_is_agent_runner(self):
        from agent_coordinator.application.runner import AgentRunner
        self.assertIsInstance(ManualRunner(), AgentRunner)

    def test_accepts_input_fn(self):
        fn = lambda prompt: "ok"
        runner = ManualRunner(input_fn=fn)
        self.assertIs(runner._input_fn, fn)


class TestManualRunnerRun(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _run_collecting_output(self, runner, message="test message", session_id=None, model=None):
        """Run and collect output via on_output callback."""
        lines = []
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", return_value=""):
                result = runner.run(message, self.workspace, session_id=session_id,
                                    model=model, on_output=lines.append)
        return result, "\n".join(lines)

    def test_returns_run_result(self):
        runner = ManualRunner(verbose=False)
        result, _ = self._run_collecting_output(runner)
        self.assertIsInstance(result, RunResult)

    def test_result_text_is_manual_turn_completed(self):
        runner = ManualRunner(verbose=False)
        result, _ = self._run_collecting_output(runner)
        self.assertEqual(result.text, "[manual turn completed by human]")

    def test_uses_provided_session_id(self):
        runner = ManualRunner(verbose=False)
        result, _ = self._run_collecting_output(runner, session_id="my-session-123")
        self.assertEqual(result.session_id, "my-session-123")

    def test_generates_session_id_when_none_provided(self):
        runner = ManualRunner(verbose=False)
        result, _ = self._run_collecting_output(runner, session_id=None)
        self.assertTrue(result.session_id.startswith("manual-"))

    def test_verbose_true_prints_prompt(self):
        runner = ManualRunner(verbose=True)
        _, output = self._run_collecting_output(runner, message="the actual prompt")
        self.assertIn("the actual prompt", output)

    def test_verbose_false_omits_prompt(self):
        runner = ManualRunner(verbose=False)
        _, output = self._run_collecting_output(runner, message="secret prompt content")
        self.assertNotIn("secret prompt content", output)

    def test_prints_workspace_path(self):
        runner = ManualRunner(verbose=False)
        _, output = self._run_collecting_output(runner, message="msg")
        self.assertIn(str(self.workspace), output)

    def test_calls_input_fn_when_provided(self):
        calls = []
        runner = ManualRunner(verbose=False, input_fn=lambda p: calls.append(p))
        runner.run("msg", self.workspace, on_output=lambda s: None)
        self.assertEqual(len(calls), 1)
        self.assertIn("Enter", calls[0])

    def test_falls_back_to_input_when_tty(self):
        runner = ManualRunner(verbose=False)
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", return_value="") as mock_input:
                runner.run("msg", self.workspace, on_output=lambda s: None)
        mock_input.assert_called_once()

    def test_skips_input_when_not_tty(self):
        runner = ManualRunner(verbose=False)
        lines = []
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            runner.run("msg", self.workspace, on_output=lines.append)
        self.assertTrue(any("not a TTY" in l for l in lines))

    def test_on_output_receives_display_lines(self):
        runner = ManualRunner(verbose=False)
        lines = []
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", return_value=""):
                runner.run("msg", self.workspace, on_output=lines.append)
        self.assertTrue(len(lines) > 0)

    def test_session_id_in_output(self):
        runner = ManualRunner(verbose=False)
        _, output = self._run_collecting_output(runner, message="msg", session_id="ses-abc")
        self.assertIn("ses-abc", output)


if __name__ == "__main__":
    unittest.main()
