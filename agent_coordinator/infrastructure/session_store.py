"""SessionStore — persists OpenCode session IDs between coordinator runs."""

from __future__ import annotations

import json
from pathlib import Path


class SessionStore:
    """Reads and writes agent session IDs to a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._sessions: dict[str, str] = self._load()

    def get(self, agent: str) -> str | None:
        """Return the saved session ID for an agent, or None."""
        return self._sessions.get(agent)

    def set(self, agent: str, session_id: str) -> None:
        """Save a session ID for an agent and persist."""
        self._sessions[agent] = session_id
        self._persist()

    def clear(self) -> None:
        """Delete all saved sessions and remove the backing file."""
        self._sessions = {}
        if self._path.exists():
            self._path.unlink()

    def all(self) -> dict[str, str]:
        """Return a copy of all session mappings."""
        return dict(self._sessions)

    def _load(self) -> dict[str, str]:
        if self._path.exists():
            return json.loads(self._path.read_text(encoding="utf-8"))
        return {}

    def _persist(self) -> None:
        self._path.write_text(
            json.dumps(self._sessions, indent=2), encoding="utf-8"
        )
