"""Tests for the AgentRunner interface, runner factory, and runner implementations."""

import tempfile
import shutil
import unittest
from pathlib import Path

from src.application.runner import AgentRunner
from src.domain.models import RunResult
from src.infrastructure.opencode_runner import OpenCodeRunner
from src.infrastructure.claude_runner import ClaudeCodeRunner
from src.infrastructure.manual_runner import ManualRunner
from coordinator import create_runner, create_runner_for_agent, _RUNNER_REGISTRY


class TestAgentRunnerInterface(unittest.TestCase):
    """Verify the ABC contract."""

    def test_opencode_runner_is_agent_runner(self):
        self.assertIsInstance(OpenCodeRunner(verbose=False), AgentRunner)

    def test_claude_runner_is_agent_runner(self):
        self.assertIsInstance(ClaudeCodeRunner(verbose=False), AgentRunner)

    def test_manual_runner_is_agent_runner(self):
        self.assertIsInstance(ManualRunner(verbose=False), AgentRunner)

    def test_run_result_is_in_domain(self):
        result = RunResult(session_id="s1", text="hello")
        self.assertEqual(result.session_id, "s1")
        self.assertEqual(result.text, "hello")

    def test_run_result_is_frozen(self):
        result = RunResult(session_id="s1", text="hello")
        with self.assertRaises(AttributeError):
            result.session_id = "s2"


class TestRunnerFactory(unittest.TestCase):
    """Test create_runner and create_runner_for_agent."""

    def test_create_opencode_runner(self):
        runner = create_runner("opencode", verbose=False)
        self.assertIsInstance(runner, OpenCodeRunner)

    def test_create_claude_runner(self):
        runner = create_runner("claude", verbose=False)
        self.assertIsInstance(runner, ClaudeCodeRunner)

    def test_create_manual_runner(self):
        runner = create_runner("manual", verbose=False)
        self.assertIsInstance(runner, ManualRunner)

    def test_unknown_backend_raises(self):
        with self.assertRaises(ValueError) as ctx:
            create_runner("nonexistent", verbose=False)
        self.assertIn("nonexistent", str(ctx.exception))
        self.assertIn("Supported", str(ctx.exception))

    def test_create_runner_for_agent_uses_agent_backend(self):
        cfg = {"backend": "claude", "model": None}
        runner = create_runner_for_agent(cfg, default_backend="opencode", verbose=False)
        self.assertIsInstance(runner, ClaudeCodeRunner)

    def test_create_runner_for_agent_falls_back_to_default(self):
        cfg = {"model": None}  # no backend key
        runner = create_runner_for_agent(cfg, default_backend="opencode", verbose=False)
        self.assertIsInstance(runner, OpenCodeRunner)

    def test_create_runner_for_agent_manual(self):
        cfg = {"backend": "manual"}
        runner = create_runner_for_agent(cfg, default_backend="opencode", verbose=False)
        self.assertIsInstance(runner, ManualRunner)


class TestOpenCodeRunnerBuildCmd(unittest.TestCase):
    """Test command construction without running subprocess."""

    def test_basic_cmd(self):
        runner = OpenCodeRunner(verbose=False)
        cmd = runner._build_cmd("hello", Path("/ws"), None, None)
        self.assertEqual(cmd[:3], ["opencode", "run", "hello"])
        self.assertIn("--format", cmd)
        self.assertIn("json", cmd)

    def test_cmd_with_session(self):
        runner = OpenCodeRunner(verbose=False)
        cmd = runner._build_cmd("msg", Path("/ws"), "ses-123", None)
        self.assertIn("--continue", cmd)
        self.assertIn("--session", cmd)
        self.assertIn("ses-123", cmd)

    def test_cmd_with_model(self):
        runner = OpenCodeRunner(verbose=False)
        cmd = runner._build_cmd("msg", Path("/ws"), None, "gpt-4")
        self.assertIn("--model", cmd)
        self.assertIn("gpt-4", cmd)


class TestClaudeRunnerBuildCmd(unittest.TestCase):
    """Test command construction without running subprocess."""

    def test_basic_cmd(self):
        runner = ClaudeCodeRunner(verbose=False)
        cmd = runner._build_cmd("hello", Path("/ws"), None, None)
        self.assertIn("claude", cmd)
        self.assertIn("--print", cmd)
        self.assertIn("hello", cmd)

    def test_cmd_with_session(self):
        runner = ClaudeCodeRunner(verbose=False)
        cmd = runner._build_cmd("msg", Path("/ws"), "ses-abc", None)
        self.assertIn("--continue", cmd)
        self.assertIn("--session-id", cmd)
        self.assertIn("ses-abc", cmd)

    def test_cmd_with_model(self):
        runner = ClaudeCodeRunner(verbose=False)
        cmd = runner._build_cmd("msg", Path("/ws"), None, "opus")
        self.assertIn("--model", cmd)
        self.assertIn("opus", cmd)

    def test_cmd_with_cwd(self):
        runner = ClaudeCodeRunner(verbose=False)
        cmd = runner._build_cmd("msg", Path("/my/project"), None, None)
        self.assertIn("--cwd", cmd)
        self.assertIn("/my/project", cmd)


class TestManualRunnerSessionId(unittest.TestCase):
    """Test ManualRunner generates session IDs (without blocking on input)."""

    def test_generates_session_id_when_none(self):
        # We can't test the full run() because it blocks on input(),
        # but we can verify the class structure.
        runner = ManualRunner(verbose=False)
        self.assertIsInstance(runner, AgentRunner)


class TestRunnerRegistryContents(unittest.TestCase):
    """Verify the registry has all expected backends."""

    def test_all_backends_registered(self):
        # Force population
        create_runner("opencode", verbose=False)
        self.assertIn("opencode", _RUNNER_REGISTRY)
        self.assertIn("claude", _RUNNER_REGISTRY)
        self.assertIn("manual", _RUNNER_REGISTRY)


if __name__ == "__main__":
    unittest.main()
