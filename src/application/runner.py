"""AgentRunner — abstract interface for agent backends.

Any tool that can receive a prompt, execute an agent turn, and return a result
implements this interface. The coordinator depends only on this abstraction,
never on a specific backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.domain.models import RunResult


class AgentRunner(ABC):
    """
    Abstract base for agent execution backends.

    Implementations include:
    - OpenCodeRunner  (opencode CLI)
    - ClaudeCodeRunner (claude CLI)
    - ManualRunner    (human-in-the-loop)
    """

    @abstractmethod
    def run(
        self,
        message: str,
        workspace: Path,
        session_id: str | None = None,
        model: str | None = None,
    ) -> RunResult:
        """
        Execute one agent turn and return the result.

        Args:
            message:    The prompt to send to the agent.
            workspace:  The working directory for the agent.
            session_id: Optional session ID for context continuity.
            model:      Optional model override.

        Returns:
            RunResult with session_id and the agent's text output.

        Raises:
            RuntimeError: If the backend fails irrecoverably.
        """
