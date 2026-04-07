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


class TestManualRunnerRun(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _run_with_no_input(self, runner, message="test message", session_id=None, model=None):
        with patch("builtins.input", return_value=""):
            with patch("sys.stdout", new_callable=StringIO):
                return runner.run(message, self.workspace, session_id=session_id, model=model)

    def test_returns_run_result(self):
        runner = ManualRunner(verbose=False)
        result = self._run_with_no_input(runner)
        self.assertIsInstance(result, RunResult)

    def test_result_text_is_manual_turn_completed(self):
        runner = ManualRunner(verbose=False)
        result = self._run_with_no_input(runner)
        self.assertEqual(result.text, "[manual turn completed by human]")

    def test_uses_provided_session_id(self):
        runner = ManualRunner(verbose=False)
        result = self._run_with_no_input(runner, session_id="my-session-123")
        self.assertEqual(result.session_id, "my-session-123")

    def test_generates_session_id_when_none_provided(self):
        runner = ManualRunner(verbose=False)
        result = self._run_with_no_input(runner, session_id=None)
        self.assertTrue(result.session_id.startswith("manual-"))

    def test_verbose_true_prints_prompt(self):
        runner = ManualRunner(verbose=True)
        captured = StringIO()
        with patch("builtins.input", return_value=""), patch("sys.stdout", captured):
            runner.run("the actual prompt", self.workspace)
        output = captured.getvalue()
        self.assertIn("the actual prompt", output)

    def test_verbose_false_omits_prompt(self):
        runner = ManualRunner(verbose=False)
        captured = StringIO()
        with patch("builtins.input", return_value=""), patch("sys.stdout", captured):
            runner.run("secret prompt content", self.workspace)
        output = captured.getvalue()
        self.assertNotIn("secret prompt content", output)

    def test_prints_workspace_path(self):
        runner = ManualRunner(verbose=False)
        captured = StringIO()
        with patch("builtins.input", return_value=""), patch("sys.stdout", captured):
            runner.run("msg", self.workspace)
        output = captured.getvalue()
        self.assertIn(str(self.workspace), output)

    def test_calls_input_to_wait(self):
        runner = ManualRunner(verbose=False)
        with patch("builtins.input", return_value="") as mock_input, \
             patch("sys.stdout", new_callable=StringIO):
            runner.run("msg", self.workspace)
        mock_input.assert_called_once()

    def test_on_output_callback_not_called(self):
        """ManualRunner ignores on_output (no subprocess)."""
        runner = ManualRunner(verbose=False)
        on_output_calls = []
        with patch("builtins.input", return_value=""), patch("sys.stdout", new_callable=StringIO):
            runner.run("msg", self.workspace, on_output=on_output_calls.append)
        self.assertEqual(on_output_calls, [])

    def test_session_id_in_output(self):
        runner = ManualRunner(verbose=False)
        captured = StringIO()
        with patch("builtins.input", return_value=""), patch("sys.stdout", captured):
            runner.run("msg", self.workspace, session_id="ses-abc")
        self.assertIn("ses-abc", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
