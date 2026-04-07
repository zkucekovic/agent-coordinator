"""OpenCodeRunner — subprocess adapter for opencode run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.domain.models import RunResult
from agent_coordinator.infrastructure.pty_utils import run_with_pty


class OpenCodeRunner(AgentRunner):
    """Runs an opencode session non-interactively via PTY."""

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

        # Collect raw JSONL lines, but also expose text chunks via on_output
        raw_lines: list[str] = []

        def _capture(line: str) -> None:
            raw_lines.append(line)

        run_with_pty(cmd, cwd=workspace, on_output=_capture)

        return self._parse_lines(raw_lines, session_id, on_output)

    def _build_cmd(self, message, workspace, session_id, model):
        cmd = ["opencode", "run", message, "--format", "json", "--dir", str(workspace)]
        if session_id:
            cmd += ["--continue", "--session", session_id]
        if model:
            cmd += ["--model", model]
        return cmd

    def _parse_lines(self, raw_lines, fallback_session_id, on_output):
        text_parts: list[str] = []
        session_id = fallback_session_id
        returncode = 0  # opencode embeds errors in JSON

        for line in raw_lines:
            try:
                event = json.loads(line)
                if event.get("type") == "text":
                    chunk = event["part"]["text"]
                    text_parts.append(chunk)
                    if on_output:
                        on_output(chunk)
                if session_id is None and "sessionID" in event:
                    session_id = event["sessionID"]
                if event.get("type") == "error":
                    returncode = 1
            except (json.JSONDecodeError, KeyError):
                pass

        if returncode != 0 and not text_parts:
            stderr = "".join(raw_lines)
            raise RuntimeError(f"opencode exited non-zero: {stderr[:200]}")

        return RunResult(session_id=session_id or "", text="".join(text_parts))

    """
    Runs an opencode session non-interactively and returns the result.

    Implements the AgentRunner interface for the OpenCode CLI backend.
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
        Invoke opencode and return (session_id, full_text_response).

        Raises RuntimeError if opencode exits non-zero with no output.
        """
        cmd = self._build_cmd(message, workspace, session_id, model)

        if self._verbose and not on_output:
            label = f"session {session_id[:12]}…" if session_id else "new session"
            print(f"  → running opencode ({label})")

        result = subprocess.run(cmd, capture_output=True, text=True)
        return self._parse_output(result, session_id, on_output)

    def _build_cmd(
        self,
        message: str,
        workspace: Path,
        session_id: str | None,
        model: str | None,
    ) -> list[str]:
        cmd = ["opencode", "run", message, "--format", "json", "--dir", str(workspace)]
        if session_id:
            cmd += ["--continue", "--session", session_id]
        if model:
            cmd += ["--model", model]
        return cmd

    def _parse_output(
        self,
        result: subprocess.CompletedProcess,
        fallback_session_id: str | None,
        on_output: Callable[[str], None] | None = None,
    ) -> RunResult:
        text_parts: list[str] = []
        session_id = fallback_session_id

        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
                if event.get("type") == "text":
                    chunk = event["part"]["text"]
                    text_parts.append(chunk)
                    if on_output:
                        on_output(chunk)
                    elif self._verbose:
                        print(chunk, end="", flush=True)
                if session_id is None and "sessionID" in event:
                    session_id = event["sessionID"]
            except (json.JSONDecodeError, KeyError):
                pass

        if self._verbose and text_parts and not on_output:
            print()

        if result.returncode != 0 and not text_parts:
            raise RuntimeError(
                f"opencode exited {result.returncode}: {result.stderr.strip()}"
            )

        return RunResult(session_id=session_id or "", text="".join(text_parts))
