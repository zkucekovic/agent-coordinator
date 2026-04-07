"""GenericRunner — configurable subprocess adapter for any CLI backend.

Supports any CLI tool that can accept a prompt and optional session/model arguments.
The command template and argument format are configured per-agent in agents.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.domain.models import RunResult
from agent_coordinator.infrastructure.pty_utils import run_with_pty


class GenericRunner(AgentRunner):
    """
    Runs any CLI backend using a configurable command template.
    
    Configuration in agents.json:
    {
        "agents": {
            "architect": {
                "backend": "custom",
                "backend_config": {
                    "command": ["my-cli", "run"],
                    "message_arg": "{message}",
                    "workspace_arg": ["--dir", "{workspace}"],
                    "session_arg": ["--session", "{session_id}"],
                    "model_arg": ["--model", "{model}"],
                    "output_format": "json",
                    "json_text_field": "result",
                    "json_session_field": "session_id"
                }
            }
        }
    }
    
    Output format options:
    - "json": Expects JSON output with configurable field names
    - "text": Treats stdout as plain text
    - "jsonl": Expects JSON lines (like opencode)
    """

    def __init__(self, config: dict[str, Any], verbose: bool = True) -> None:
        self._verbose = verbose
        self._config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Ensure required config fields are present."""
        if "command" not in self._config:
            raise ValueError("backend_config must include 'command' field")
        if not isinstance(self._config["command"], list):
            raise ValueError("backend_config.command must be a list")

    def run(
        self,
        message: str,
        workspace: Path,
        session_id: str | None = None,
        model: str | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> RunResult:
        """
        Invoke the configured CLI tool and return the result.
        
        Raises RuntimeError if the command exits non-zero with no output.
        """
        cmd = self._build_cmd(message, workspace, session_id, model)

        if self._verbose:
            tool_name = self._config["command"][0]
            label = f"session {session_id[:12]}…" if session_id else "new session"
            print(f"  → running {tool_name} ({label})")

        result = run_with_pty(cmd, cwd=workspace, on_output=on_output)
        return self._parse_output(result, session_id)

    def _build_cmd(
        self,
        message: str,
        workspace: Path,
        session_id: str | None,
        model: str | None,
    ) -> list[str]:
        """Build the command list with all configured arguments."""
        cmd = list(self._config["command"])
        
        # Add message argument
        message_arg = self._config.get("message_arg", "{message}")
        cmd.append(message_arg.format(message=message))
        
        # Add workspace argument if configured
        if "workspace_arg" in self._config:
            workspace_arg = self._config["workspace_arg"]
            cmd.extend(self._format_arg_list(workspace_arg, workspace=str(workspace)))
        
        # Add session argument if provided and configured
        if session_id and "session_arg" in self._config:
            session_arg = self._config["session_arg"]
            cmd.extend(self._format_arg_list(session_arg, session_id=session_id))
        
        # Add model argument if provided and configured
        if model and "model_arg" in self._config:
            model_arg = self._config["model_arg"]
            cmd.extend(self._format_arg_list(model_arg, model=model))
        
        return cmd

    def _format_arg_list(self, arg_template: list[str] | str, **kwargs: str) -> list[str]:
        """Format a list of arguments with provided variables."""
        if isinstance(arg_template, str):
            return [arg_template.format(**kwargs)]
        return [arg.format(**kwargs) for arg in arg_template]

    def _parse_output(
        self,
        result,
        fallback_session_id: str | None,
    ) -> RunResult:
        """Parse output based on configured format."""
        output_format = self._config.get("output_format", "text")
        
        if output_format == "jsonl":
            return self._parse_jsonl(result, fallback_session_id)
        elif output_format == "json":
            return self._parse_json(result, fallback_session_id)
        else:
            return self._parse_text(result, fallback_session_id)

    def _parse_jsonl(
        self,
        result,
        fallback_session_id: str | None,
    ) -> RunResult:
        """Parse JSON lines output (like opencode)."""
        text_parts: list[str] = []
        session_id = fallback_session_id
        text_field = self._config.get("json_text_field", "text")
        session_field = self._config.get("json_session_field", "sessionID")

        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
                
                # Extract session ID if present
                if session_id is None and session_field in event:
                    session_id = event[session_field]
                
                # Check for text in various possible structures
                if text_field in event:
                    chunk = event[text_field]
                    text_parts.append(chunk)
                    if self._verbose:
                        print(chunk, end="", flush=True)
                elif "part" in event and text_field in event["part"]:
                    chunk = event["part"][text_field]
                    text_parts.append(chunk)
                    if self._verbose:
                        print(chunk, end="", flush=True)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        if self._verbose and text_parts:
            print()

        if result.returncode != 0 and not text_parts:
            raise RuntimeError(
                f"Command exited {result.returncode}: {result.stderr.strip()}"
            )

        return RunResult(session_id=session_id or "", text="".join(text_parts))

    def _parse_json(
        self,
        result,
        fallback_session_id: str | None,
    ) -> RunResult:
        """Parse JSON object output (like claude --print)."""
        text = ""
        session_id = fallback_session_id
        text_field = self._config.get("json_text_field", "result")
        session_field = self._config.get("json_session_field", "session_id")

        try:
            data = json.loads(result.stdout)
            text = data.get(text_field, result.stdout)
            session_id = data.get(session_field, fallback_session_id)
            if self._verbose and text:
                print(text)
        except (json.JSONDecodeError, TypeError):
            text = result.stdout
            if self._verbose and text:
                print(text)

        if result.returncode != 0 and not text:
            raise RuntimeError(
                f"Command exited {result.returncode}: {result.stderr.strip()}"
            )

        return RunResult(session_id=session_id or "", text=text)

    def _parse_text(
        self,
        result,
        fallback_session_id: str | None,
    ) -> RunResult:
        """Parse plain text output."""
        text = result.stdout
        
        if self._verbose and text:
            print(text)

        if result.returncode != 0 and not text:
            raise RuntimeError(
                f"Command exited {result.returncode}: {result.stderr.strip()}"
            )

        return RunResult(session_id=fallback_session_id or "", text=text)
