"""ManualRunner — human-in-the-loop agent backend.

Pauses the coordinator and waits for a human to perform the agent's work
manually. The human reads the prompt, does the work, updates handoff.md,
and presses Enter to continue.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Callable

from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.domain.models import RunResult


class ManualRunner(AgentRunner):
    """
    Human-in-the-loop runner. Displays the prompt and waits for the human
    to act, then returns a stub result.

    Useful for:
    - Mixed workflows where some agents are AI and others are human
    - Debugging and development of new agent prompts
    - Environments where a specific tool is not available
    """

    def __init__(self, verbose: bool = True, input_fn: Callable[[str], str] | None = None) -> None:
        self._verbose = verbose
        self._input_fn = input_fn

    def run(
        self,
        message: str,
        workspace: Path,
        session_id: str | None = None,
        model: str | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> RunResult:
        """
        Display the prompt and wait for the human to act.

        The human is expected to:
        1. Read the displayed prompt
        2. Perform the work in the workspace
        3. Update handoff.md with a valid handoff block
        4. Press Enter to continue
        """
        sid = session_id or f"manual-{uuid.uuid4().hex[:8]}"

        emit = on_output or (lambda s: print(s, file=sys.stderr))

        sep = "═" * 60
        emit(f"\n{sep}")
        emit("  MANUAL TURN — Human action required")
        emit(f"  Workspace: {workspace}")
        emit(f"  Session:   {sid}")
        emit(sep)

        if self._verbose:
            emit(f"\n--- Prompt ---\n{message}\n--- End prompt ---\n")

        emit(f"Perform your work in: {workspace}")
        emit(f"Then update: {workspace}/handoff.md")

        prompt_text = "\nPress Enter when done → "
        if self._input_fn:
            self._input_fn(prompt_text)
        elif sys.stdin.isatty():
            input(prompt_text)
        else:
            emit("(stdin is not a TTY — skipping interactive prompt)")

        return RunResult(session_id=sid, text="[manual turn completed by human]")
