"""Unit tests for pure/utility functions in agent_coordinator/cli.py."""

from __future__ import annotations

import argparse
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from agent_coordinator.cli import (
    _DEFAULT_AGENTS,
    _create_initial_handoff,
    _execute_startup_action,
    _file_hash,
    _handle_popup_command,
    _retry_prompt,
    load_agent_config,
    load_config,
    load_retry_policy,
)
from agent_coordinator.domain.retry_policy import RetryPolicy


def _make_args(workspace: Path) -> argparse.Namespace:
    return argparse.Namespace(
        max_turns=30,
        quiet=False,
        output_lines=10,
        no_streaming=False,
        workspace=workspace,
    )


def _make_display() -> MagicMock:
    display = MagicMock()
    display._theme.color_success = ""
    display._theme.color_warning = ""
    display._theme.text_dim = ""
    display.read_input.return_value = ""
    display._append_content = MagicMock()
    return display


class TestLoadConfig(unittest.TestCase):
    def test_no_agents_json_returns_empty_dict(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            self.assertEqual(load_config(ws), {})

    def test_workspace_agents_json_is_returned(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            cfg = {"default_backend": "copilot"}
            (ws / "agents.json").write_text(json.dumps(cfg))
            self.assertEqual(load_config(ws), cfg)

    def test_parent_agents_json_fallback(self):
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            ws = parent / "ws"
            ws.mkdir()
            cfg = {"default_backend": "claude"}
            (parent / "agents.json").write_text(json.dumps(cfg))
            self.assertEqual(load_config(ws), cfg)

    def test_workspace_takes_precedence_over_parent(self):
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            ws = parent / "ws"
            ws.mkdir()
            (parent / "agents.json").write_text(json.dumps({"source": "parent"}))
            (ws / "agents.json").write_text(json.dumps({"source": "workspace"}))
            result = load_config(ws)
            self.assertEqual(result["source"], "workspace")


class TestLoadAgentConfig(unittest.TestCase):
    def test_empty_config_returns_defaults(self):
        result = load_agent_config({})
        self.assertEqual(result, _DEFAULT_AGENTS)

    def test_none_config_returns_defaults(self):
        result = load_agent_config(None)
        self.assertEqual(result, _DEFAULT_AGENTS)

    def test_custom_agents_returned(self):
        cfg = {"agents": {"x": {"prompt_file": "p.md"}}}
        result = load_agent_config(cfg)
        self.assertEqual(result, {"x": {"prompt_file": "p.md"}})

    def test_config_without_agents_key_returns_defaults(self):
        result = load_agent_config({"default_backend": "copilot"})
        self.assertEqual(result, _DEFAULT_AGENTS)


class TestLoadRetryPolicy(unittest.TestCase):
    def test_empty_config_returns_default(self):
        policy = load_retry_policy({})
        self.assertIsInstance(policy, RetryPolicy)
        self.assertEqual(policy.max_rework, 3)
        self.assertEqual(policy.on_exceed, "needs_human")

    def test_custom_retry_policy(self):
        cfg = {"retry_policy": {"max_rework": 5, "on_exceed": "needs_human"}}
        policy = load_retry_policy(cfg)
        self.assertEqual(policy.max_rework, 5)
        self.assertEqual(policy.on_exceed, "needs_human")

    def test_no_retry_policy_key_returns_default(self):
        policy = load_retry_policy({"default_backend": "copilot"})
        self.assertIsInstance(policy, RetryPolicy)
        self.assertEqual(policy.max_rework, 3)


class TestFileHash(unittest.TestCase):
    def test_nonexistent_path_returns_empty_string(self):
        self.assertEqual(_file_hash(Path("/nonexistent_file_xyz_abc")), "")

    def test_real_file_returns_64_char_hex(self):
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.txt"
            f.write_text("hello world")
            result = _file_hash(f)
            self.assertEqual(len(result), 64)
            self.assertRegex(result, r"^[0-9a-f]{64}$")

    def test_hash_changes_when_file_changes(self):
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.txt"
            f.write_text("content v1")
            h1 = _file_hash(f)
            f.write_text("content v2")
            h2 = _file_hash(f)
            self.assertNotEqual(h1, h2)

    def test_same_content_same_hash(self):
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.txt"
            f.write_bytes(b"deterministic")
            self.assertEqual(_file_hash(f), _file_hash(f))


class TestRetryPrompt(unittest.TestCase):
    def test_no_handoff_md_contains_handoff_markers(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            result = _retry_prompt("developer", ws)
            self.assertIn("---HANDOFF---", result)
            self.assertIn("---END---", result)

    def test_contains_did_not_append(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            result = _retry_prompt("developer", ws)
            self.assertIn("did NOT append", result)

    def test_existing_handoff_includes_first_10_lines_only(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            lines = [f"line-{i}" for i in range(15)]
            (ws / "handoff.md").write_text("\n".join(lines))
            result = _retry_prompt("developer", ws)
            self.assertIn("line-0", result)
            self.assertIn("line-9", result)
            self.assertNotIn("line-10", result)

    def test_no_handoff_md_snippet_is_empty(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            result = _retry_prompt("developer", ws)
            # The snippet section should be empty (no actual file content)
            self.assertIn("Current handoff.md (first 10 lines):\n\n", result)


class TestCreateInitialHandoff(unittest.TestCase):
    def test_creates_handoff_md(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            _create_initial_handoff(ws)
            self.assertTrue((ws / "handoff.md").exists())

    def test_handoff_md_contains_block(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            _create_initial_handoff(ws)
            content = (ws / "handoff.md").read_text()
            self.assertIn("---HANDOFF---", content)
            self.assertIn("---END---", content)


class TestHandlePopupCommand(unittest.TestCase):
    def test_reset_command_clears_session_and_calls_append(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            display = _make_display()
            _handle_popup_command("x", ws, display)
            display._append_content.assert_called()

    def test_reset_command_does_not_raise(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            display = _make_display()
            # Should not raise even if session file doesn't exist
            _handle_popup_command("x", ws, display)


class TestExecuteStartupAction(unittest.TestCase):
    def _make_args(self) -> argparse.Namespace:
        return _make_args(Path("workspace"))

    def test_quit_with_no_screen_does_not_raise(self):
        args = self._make_args()
        # screen=None, so the `if screen and screen._active` branch is skipped
        _execute_startup_action({"action": "quit", "screen": None}, args)

    def test_reset_with_no_screen_clears_session(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            args = self._make_args()
            # Should not raise
            _execute_startup_action({"action": "reset", "workspace": ws, "screen": None}, args)

    def test_init_with_no_screen_creates_workspace_and_handoff(self):
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "new_ws"
            args = self._make_args()
            _execute_startup_action({"action": "init", "workspace": ws, "screen": None}, args)
            self.assertTrue(ws.exists())
            self.assertTrue((ws / "handoff.md").exists())


if __name__ == "__main__":
    unittest.main()
