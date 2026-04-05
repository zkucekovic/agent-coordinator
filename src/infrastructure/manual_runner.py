"""ManualRunner — human-in-the-loop agent backend.

Pauses the coordinator and waits for a human to perform the agent's work
manually. The human reads the prompt, does the work, updates handoff.md,
and presses Enter to continue.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from src.application.runner import AgentRunner
from src.domain.models import RunResult


class ManualRunner(AgentRunner):
    """
    Human-in-the-loop runner. Displays the prompt and waits for the human
    to act, then returns a stub result.

    Useful for:
    - Mixed workflows where some agents are AI and others are human
    - Debugging and development of new agent prompts
    - Environments where a specific tool is not available
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
        Display the prompt and wait for the human to act.

        The human is expected to:
        1. Read the displayed prompt
        2. Perform the work in the workspace
        3. Update handoff.md with a valid handoff block
        4. Press Enter to continue
        """
        sid = session_id or f"manual-{uuid.uuid4().hex[:8]}"

        print(f"\n{'═' * 60}")
        print(f"  MANUAL TURN — Human action required")
        print(f"  Workspace: {workspace}")
        print(f"  Session:   {sid}")
        print(f"{'═' * 60}")

        if self._verbose:
            print(f"\n--- Prompt ---\n{message}\n--- End prompt ---\n")

        print(f"Perform your work in: {workspace}")
        print(f"Then update: {workspace}/handoff.md")
        input("\nPress Enter when done → ")

        return RunResult(session_id=sid, text="[manual turn completed by human]")
