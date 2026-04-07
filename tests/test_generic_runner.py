"""Tests for GenericRunner — custom backend support."""

import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from agent_coordinator.infrastructure.generic_runner import GenericRunner
from agent_coordinator.domain.models import RunResult


class TestGenericRunner(unittest.TestCase):
    """Test the GenericRunner with various configurations."""

    def test_validate_config_requires_command(self):
        """GenericRunner raises ValueError if command is missing."""
        with self.assertRaises(ValueError) as ctx:
            GenericRunner({}, verbose=False)
        self.assertIn("command", str(ctx.exception))

    def test_validate_config_requires_list_command(self):
        """GenericRunner raises ValueError if command is not a list."""
        with self.assertRaises(ValueError) as ctx:
            GenericRunner({"command": "my-tool"}, verbose=False)
        self.assertIn("must be a list", str(ctx.exception))

    @patch("subprocess.run")
    def test_text_output_format(self, mock_run):
        """GenericRunner can parse plain text output."""
        mock_result = MagicMock()
        mock_result.stdout = "Agent response text"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        config = {
            "command": ["my-tool", "run"],
            "output_format": "text",
        }
        runner = GenericRunner(config, verbose=False)
        result = runner.run("Test message", Path("/tmp"), session_id=None, model=None)

        self.assertEqual(result.text, "Agent response text")
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_json_output_format(self, mock_run):
        """GenericRunner can parse JSON output."""
        mock_result = MagicMock()
        mock_result.stdout = '{"result": "JSON response", "session_id": "sess123"}'
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        config = {
            "command": ["my-tool", "run"],
            "output_format": "json",
            "json_text_field": "result",
            "json_session_field": "session_id",
        }
        runner = GenericRunner(config, verbose=False)
        result = runner.run("Test message", Path("/tmp"), session_id=None, model=None)

        self.assertEqual(result.text, "JSON response")
        self.assertEqual(result.session_id, "sess123")

    @patch("subprocess.run")
    def test_jsonl_output_format(self, mock_run):
        """GenericRunner can parse JSON lines output."""
        mock_result = MagicMock()
        mock_result.stdout = (
            '{"sessionID": "abc123"}\n'
            '{"type": "text", "part": {"text": "First chunk"}}\n'
            '{"type": "text", "part": {"text": " Second chunk"}}\n'
        )
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        config = {
            "command": ["my-tool", "run"],
            "output_format": "jsonl",
            "json_text_field": "text",
            "json_session_field": "sessionID",
        }
        runner = GenericRunner(config, verbose=False)
        result = runner.run("Test message", Path("/tmp"), session_id=None, model=None)

        self.assertEqual(result.text, "First chunk Second chunk")
        self.assertEqual(result.session_id, "abc123")

    @patch("subprocess.run")
    def test_command_building_with_all_args(self, mock_run):
        """GenericRunner builds command with all configured arguments."""
        mock_result = MagicMock()
        mock_result.stdout = "response"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        config = {
            "command": ["my-tool", "run"],
            "message_arg": "--prompt={message}",
            "workspace_arg": ["--dir", "{workspace}"],
            "session_arg": ["--session", "{session_id}"],
            "model_arg": ["--model", "{model}"],
            "output_format": "text",
        }
        runner = GenericRunner(config, verbose=False)
        runner.run(
            message="test prompt",
            workspace=Path("/tmp/workspace"),
            session_id="sess123",
            model="gpt-4",
        )

        # Get the actual command that was called
        called_cmd = mock_run.call_args[0][0]
        
        self.assertEqual(called_cmd[0:2], ["my-tool", "run"])
        self.assertIn("--prompt=test prompt", called_cmd)
        self.assertIn("--dir", called_cmd)
        self.assertIn("/tmp/workspace", called_cmd)
        self.assertIn("--session", called_cmd)
        self.assertIn("sess123", called_cmd)
        self.assertIn("--model", called_cmd)
        self.assertIn("gpt-4", called_cmd)

    @patch("subprocess.run")
    def test_command_building_without_optional_args(self, mock_run):
        """GenericRunner omits unconfigured optional arguments."""
        mock_result = MagicMock()
        mock_result.stdout = "response"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        config = {
            "command": ["my-tool", "run"],
            "message_arg": "{message}",
            "output_format": "text",
        }
        runner = GenericRunner(config, verbose=False)
        runner.run(
            message="test prompt",
            workspace=Path("/tmp/workspace"),
            session_id="sess123",
            model="gpt-4",
        )

        called_cmd = mock_run.call_args[0][0]
        
        # Should have command + message only
        self.assertEqual(called_cmd, ["my-tool", "run", "test prompt"])

    @patch("subprocess.run")
    def test_error_handling_nonzero_exit(self, mock_run):
        """GenericRunner raises RuntimeError on non-zero exit with no output."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Command failed"
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        config = {
            "command": ["my-tool", "run"],
            "output_format": "text",
        }
        runner = GenericRunner(config, verbose=False)
        
        with self.assertRaises(RuntimeError) as ctx:
            runner.run("test", Path("/tmp"), None, None)
        
        self.assertIn("exited 1", str(ctx.exception))

    @patch("subprocess.run")
    def test_custom_json_fields(self, mock_run):
        """GenericRunner can use custom JSON field names."""
        mock_result = MagicMock()
        mock_result.stdout = '{"response": "Custom response", "id": "custom123"}'
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        config = {
            "command": ["my-tool"],
            "output_format": "json",
            "json_text_field": "response",
            "json_session_field": "id",
        }
        runner = GenericRunner(config, verbose=False)
        result = runner.run("Test", Path("/tmp"), None, None)

        self.assertEqual(result.text, "Custom response")
        self.assertEqual(result.session_id, "custom123")


if __name__ == "__main__":
    unittest.main()
