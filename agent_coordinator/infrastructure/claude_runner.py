"""ClaudeCodeRunner — subprocess adapter for the Claude Code CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.domain.models import RunResult
from agent_coordinator.infrastructure.pty_utils import run_with_pty


class ClaudeCodeRunner(AgentRunner):
    """Runs a Claude Code CLI session non-interactively via PTY."""

    def __init__(self, verbose: bool = True) -> None:
        self._verbose = verbose

    def run(
        self,
        message: str,
        workspace: Path,
        session_id: str | None = None,
        model: str | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> RunResult:
        cmd = self._build_cmd(message, workspace, session_id, model)
        result = run_with_pty(cmd, cwd=workspace, on_output=on_output)
        return self._parse_output(result, session_id)

    def _build_cmd(self, message, workspace, session_id, model):
        cmd = ["claude", "--print", "--output-format", "json"]
        if session_id:
            cmd += ["--continue", "--session-id", session_id]
        if model:
            cmd += ["--model", model]
        cmd += ["--cwd", str(workspace), message]
        return cmd

    def _parse_output(self, result, fallback_session_id):
        text = ""
        session_id = fallback_session_id
        try:
            data = json.loads(result.stdout)
            text = data.get("result", result.stdout)
            session_id = data.get("session_id", fallback_session_id)
        except (json.JSONDecodeError, TypeError):
            text = result.stdout
        if result.returncode != 0 and not text:
            raise RuntimeError(
                f"claude exited {result.returncode}: {result.stderr}"
            )
        return RunResult(session_id=session_id or "", text=text)

    """
    Runs a Claude Code CLI session non-interactively and returns the result.

    Requires the `claude` CLI to be installed and authenticated.
    Uses --print mode for non-interactive output.
    """

    def __init__(self, verbose: bool = True) -> None:
        self._verbose = verbose

    def run(
        self,
        message: str,
        workspace: Path,
        session_id: str | None = None,
        model: str | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> RunResult:
        """
        Invoke claude CLI and return the result.

        Raises RuntimeError if claude exits non-zero with no output.
        """
        cmd = self._build_cmd(message, workspace, session_id, model)

        if self._verbose:
            label = f"session {session_id[:12]}…" if session_id else "new session"
            print(f"  → running claude ({label})")

        result = subprocess.run(cmd, capture_output=True, text=True)
        return self._parse_output(result, session_id)

    def _build_cmd(
        self,
        message: str,
        workspace: Path,
        session_id: str | None,
        model: str | None,
    ) -> list[str]:
        cmd = ["claude", "--print", "--output-format", "json"]
        if session_id:
            cmd += ["--continue", "--session-id", session_id]
        if model:
            cmd += ["--model", model]
        cmd += ["--cwd", str(workspace), message]
        return cmd

    def _parse_output(
        self,
        result: subprocess.CompletedProcess,
        fallback_session_id: str | None,
    ) -> RunResult:
        text = ""
        session_id = fallback_session_id

        # Claude --print --output-format json returns a JSON object
        try:
            data = json.loads(result.stdout)
            text = data.get("result", result.stdout)
            session_id = data.get("session_id", fallback_session_id)
            if self._verbose and text:
                print(text)
        except (json.JSONDecodeError, TypeError):
            # Fallback: treat stdout as plain text
            text = result.stdout
            if self._verbose and text:
                print(text)

        if result.returncode != 0 and not text:
            raise RuntimeError(
                f"claude exited {result.returncode}: {result.stderr.strip()}"
            )

        return RunResult(session_id=session_id or "", text=text)
