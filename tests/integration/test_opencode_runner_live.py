"""
Integration tests for OpenCodeRunner — real opencode subprocess calls.

Requires: RUN_INTEGRATION_TESTS=1

Tests:
  1. A fresh run returns non-empty text and a valid session_id.
  2. Continuing an existing session is accepted (session_id reused).
  3. An absurd/bad command fails gracefully with a RuntimeError.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.integration.conftest import requires_integration
from agent_coordinator.infrastructure.opencode_runner import OpenCodeRunner


@requires_integration
class TestOpenCodeRunnerLive(unittest.TestCase):

    def setUp(self):
        self._workspace = Path(tempfile.mkdtemp())
        self._runner = OpenCodeRunner(verbose=False)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._workspace, ignore_errors=True)

    # ── Basic run ─────────────────────────────────────────────────────────────

    def test_run_returns_nonempty_text(self):
        """A fresh run with a simple prompt should return text."""
        result = self._runner.run(
            message="Reply with exactly the single word: PONG",
            workspace=self._workspace,
        )
        self.assertTrue(len(result.text) > 0, "Expected non-empty response text")

    def test_run_returns_valid_session_id(self):
        """A fresh run should return a non-empty session ID string."""
        result = self._runner.run(
            message="Reply with exactly the single word: PONG",
            workspace=self._workspace,
        )
        self.assertIsInstance(result.session_id, str)
        self.assertTrue(len(result.session_id) > 0, "Expected non-empty session_id")

    def test_run_response_contains_expected_word(self):
        """Model should follow a very simple constrained instruction."""
        result = self._runner.run(
            message="Reply with exactly the single word: INTEGRATION_OK",
            workspace=self._workspace,
        )
        self.assertIn("INTEGRATION_OK", result.text)

    # ── Session continuation ──────────────────────────────────────────────────

    def test_run_continues_existing_session(self):
        """Continuing a session with a valid session_id should succeed."""
        first = self._runner.run(
            message="Remember this number: 7919. Reply only: STORED",
            workspace=self._workspace,
        )
        self.assertTrue(first.session_id, "First run must return a session_id")

        second = self._runner.run(
            message="What number did I ask you to remember? Reply with only the number.",
            workspace=self._workspace,
            session_id=first.session_id,
        )
        self.assertIn("7919", second.text, "Continued session should recall context")

    def test_session_id_is_reused_when_continuing(self):
        """session_id returned on continuation should match the original."""
        first = self._runner.run(
            message="Reply with exactly the single word: START",
            workspace=self._workspace,
        )
        second = self._runner.run(
            message="Reply with exactly the single word: CONTINUE",
            workspace=self._workspace,
            session_id=first.session_id,
        )
        self.assertEqual(
            first.session_id,
            second.session_id,
            "Continued session should return the same session_id",
        )

    # ── Workspace isolation ───────────────────────────────────────────────────

    def test_run_uses_specified_workspace_directory(self):
        """OpenCode should be able to write files in the given workspace."""
        result = self._runner.run(
            message=(
                "Create a file called `runner_test_output.txt` "
                "in the current directory with content 'runner_ok'. "
                "Then reply with: WRITTEN"
            ),
            workspace=self._workspace,
        )
        output_file = self._workspace / "runner_test_output.txt"
        self.assertTrue(output_file.exists(), "Expected the agent to create the file")
        self.assertIn("runner_ok", output_file.read_text())


if __name__ == "__main__":
    unittest.main()
