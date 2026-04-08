"""OpenCodeRunner — subprocess adapter for opencode run."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

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

    def _parse_lines(
        self,
        raw_lines: list[str],
        fallback_session_id: str | None,
        on_output: Callable[[str], None] | None,
    ) -> RunResult:
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
            except (json.JSONDecodeError, KeyError):  # noqa: PERF203
                pass

        if returncode != 0 and not text_parts:
            stderr = "".join(raw_lines)
            raise RuntimeError(f"opencode exited non-zero: {stderr[:200]}")

        return RunResult(session_id=session_id or "", text="".join(text_parts))
