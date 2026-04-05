"""OpenCodeRunner — subprocess adapter for opencode run.

All subprocess interaction is contained here. The rest of the application
works with plain Python strings and never touches subprocess directly.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunResult:
    session_id: str
    text: str


class OpenCodeRunner:
    """
    Runs an opencode session non-interactively and returns the result.

    Separating this from the coordinator makes it straightforward to:
    - stub in tests (replace with a fake that writes to handoff.md)
    - swap for a different backend (e.g. a local model runner)
    """

    def __init__(self, verbose: bool = True) -> None:
        self._verbose = verbose

    def run(
        self,
        message: str,
        workspace: Path,
        session_id: str | None = None,
        model: str | None = None,
    ) -> RunResult:
        """
        Invoke opencode and return (session_id, full_text_response).

        Raises RuntimeError if opencode exits non-zero with no output.
        """
        cmd = self._build_cmd(message, workspace, session_id, model)

        if self._verbose:
            label = f"session {session_id[:12]}…" if session_id else "new session"
            print(f"  → running opencode ({label})")

        result = subprocess.run(cmd, capture_output=True, text=True)
        return self._parse_output(result, session_id)

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
    ) -> RunResult:
        text_parts: list[str] = []
        session_id = fallback_session_id

        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
                if event.get("type") == "text":
                    chunk = event["part"]["text"]
                    text_parts.append(chunk)
                    if self._verbose:
                        print(chunk, end="", flush=True)
                if session_id is None and "sessionID" in event:
                    session_id = event["sessionID"]
            except (json.JSONDecodeError, KeyError):
                pass

        if self._verbose and text_parts:
            print()

        if result.returncode != 0 and not text_parts:
            raise RuntimeError(
                f"opencode exited {result.returncode}: {result.stderr.strip()}"
            )

        return RunResult(session_id=session_id or "", text="".join(text_parts))
