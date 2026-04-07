"""CopilotRunner — subprocess adapter for GitHub Copilot CLI.

Supports `copilot` CLI for non-interactive execution.
Uses the copilot command with --prompt mode.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.domain.models import RunResult


class CopilotRunner(AgentRunner):
    """
    Runs GitHub Copilot CLI session non-interactively and returns the result.

    Requires the `copilot` CLI to be installed.
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
        Invoke copilot CLI and return the result.

        If on_output is provided, lines are streamed in real time as the
        process writes them. Otherwise output is captured and printed at end.

        Raises RuntimeError if copilot exits non-zero with no output.
        """
        cmd = self._build_cmd(message, workspace, session_id, model)

        if on_output:
            return self._run_streaming(cmd, workspace, session_id, on_output)

        if self._verbose:
            label = f"session {session_id[:12]}…" if session_id else "new session"
            print(f"  → running copilot ({label})")

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=workspace)
        return self._parse_output(result, session_id, on_output=None)

    def _run_streaming(
        self,
        cmd: list[str],
        workspace: Path,
        session_id: str | None,
        on_output: Callable[[str], None],
    ) -> RunResult:
        """Run copilot and stream stdout line-by-line via on_output callback."""
        lines: list[str] = []
        stderr_lines: list[str] = []

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=workspace,
        )

        # Stream stdout in real time
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            on_output(line)

        # Collect stderr after stdout closes
        assert proc.stderr is not None
        stderr_lines = proc.stderr.readlines()

        proc.wait()

        stdout_text = "".join(lines).strip()
        stderr_text = "".join(stderr_lines).strip()

        if proc.returncode != 0 and not stdout_text:
            raise RuntimeError(
                f"copilot exited {proc.returncode}: {stderr_text}"
            )

        resolved_session = self._extract_session_id(stderr_text, session_id, stdout_text)
        return RunResult(session_id=resolved_session, text=stdout_text)

    def _build_cmd(
        self,
        message: str,
        workspace: Path,
        session_id: str | None,
        model: str | None,
    ) -> list[str]:
        """Build the copilot command."""
        cmd = [
            "copilot",
            "--prompt", message,
            "--allow-all-tools",  # Required for non-interactive mode
            "--no-color"  # Better for parsing
        ]
        
        # Add model if specified
        if model:
            cmd.extend(["--model", model])
        
        # Resume session if provided
        if session_id:
            cmd.extend(["--resume", session_id])
        
        return cmd

    def _parse_output(
        self,
        result: subprocess.CompletedProcess,
        fallback_session_id: str | None,
        on_output: Callable[[str], None] | None = None,
    ) -> RunResult:
        """Parse output from a completed (non-streaming) copilot run."""
        text = result.stdout.strip()

        if self._verbose and text:
            print(text)

        session_id = self._extract_session_id(result.stderr, fallback_session_id, text)

        if result.returncode != 0 and not text:
            raise RuntimeError(
                f"copilot exited {result.returncode}: {result.stderr.strip()}"
            )

        return RunResult(session_id=session_id or "", text=text)

    def _extract_session_id(
        self,
        stderr: str,
        fallback: str | None,
        stdout: str,
    ) -> str:
        """Extract a real UUID session ID from stderr output, or return the fallback.

        Never generates a fake ID — copilot only accepts valid UUIDs for --resume.
        Returns "" if no valid session ID is found (triggers a fresh session next run).
        """
        import re
        _UUID_RE = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            re.IGNORECASE,
        )

        # Prefer a UUID found in stderr (copilot session tracking output)
        if stderr:
            match = _UUID_RE.search(stderr)
            if match:
                return match.group(0)

        # Keep the existing session if it's a real UUID
        if fallback and _UUID_RE.fullmatch(fallback):
            return fallback

        # No valid UUID — return empty so _build_cmd skips --resume
        return ""

