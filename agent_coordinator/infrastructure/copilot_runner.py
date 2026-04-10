"""CopilotRunner — subprocess adapter for GitHub Copilot CLI."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.domain.models import RunResult
from agent_coordinator.infrastructure.pty_utils import run_with_pty


class CopilotRunner(AgentRunner):
    """Runs GitHub Copilot CLI via PTY so permission dialogs work."""

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
        # Write the prompt to a temp file and pass @path to avoid hitting the
        # OS ARG_MAX limit when prompts include large spec/plan documents.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(message)
            prompt_arg = f"@{tf.name}"

        try:
            cmd = self._build_cmd(prompt_arg, workspace, session_id, model)
            result = run_with_pty(cmd, cwd=workspace, on_output=on_output)
        finally:
            Path(tf.name).unlink(missing_ok=True)

        if result.returncode != 0 and not result.stdout:
            raise RuntimeError(f"copilot exited {result.returncode}: {result.stderr}")

        session = self._extract_session_id(result.stderr, session_id, result.stdout)
        return RunResult(session_id=session, text=result.stdout)

    def _build_cmd(self, prompt_arg: str, workspace: Path, session_id: str | None, model: str | None) -> list[str]:  # noqa: ARG002
        cmd = ["copilot", "--prompt", prompt_arg, "--allow-all", "--no-color"]
        if model:
            cmd.extend(["--model", model])
        if session_id:
            cmd.extend(["--resume", session_id])
        return cmd

    def _extract_session_id(self, stderr: str, fallback: str | None, stdout: str) -> str:  # noqa: ARG002
        import re

        uuid_re = re.compile(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            re.IGNORECASE,
        )
        if stderr:
            m = uuid_re.search(stderr)
            if m:
                return m.group(0)
        if fallback and uuid_re.fullmatch(fallback):
            return fallback
        return ""
