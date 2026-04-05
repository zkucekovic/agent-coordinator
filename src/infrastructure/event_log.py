"""EventLog — appends one structured JSON record per turn to workflow_events.jsonl.

Provides a machine-readable audit trail of the full coordination run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class EventLog:
    """Appends turn events to a JSONL file (one JSON object per line)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(
        self,
        turn: int,
        agent: str,
        task_id: str,
        status_before: str,
        status_after: str,
        session_id: str,
        extra: dict | None = None,
    ) -> None:
        """
        Append one event record.

        Args:
            turn:           Turn number (1-based).
            agent:          Agent role name (e.g. "architect").
            task_id:        TASK_ID from the handoff block.
            status_before:  HandoffStatus before this turn.
            status_after:   HandoffStatus after this turn.
            session_id:     OpenCode session ID used for this turn.
            extra:          Optional dict of additional fields to include.
        """
        record: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "turn": turn,
            "agent": agent,
            "task_id": task_id,
            "status_before": status_before,
            "status_after": status_after,
            "session_id": session_id,
        }
        if extra:
            record.update(extra)

        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def read_all(self) -> list[dict]:
        """Return all logged events as a list of dicts."""
        if not self._path.exists():
            return []
        events = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events
