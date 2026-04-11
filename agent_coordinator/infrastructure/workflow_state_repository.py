"""Persistence for coordinator workflow state."""

from __future__ import annotations

import json
from pathlib import Path

from agent_coordinator.domain.models import WorkflowState

_CURRENT_VERSION = 1


class WorkflowStateRepository:
    """File-backed repository for workflow runtime state."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> WorkflowState:
        if not self._path.exists():
            return WorkflowState(version=_CURRENT_VERSION)
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return WorkflowState(
            version=int(raw.get("version", _CURRENT_VERSION)),
            pending_task_id=raw.get("pending_task_id", ""),
            pending_actor=raw.get("pending_actor", ""),
            pending_status=raw.get("pending_status", ""),
            pending_summary=raw.get("pending_summary", ""),
            last_transition_key=raw.get("last_transition_key", ""),
            transition_keys=list(raw.get("transition_keys", [])),
            no_progress_turns=int(raw.get("no_progress_turns", 0)),
            recovery_count=int(raw.get("recovery_count", 0)),
        )

    def save(self, state: WorkflowState) -> None:
        payload = {
            "version": _CURRENT_VERSION,
            "pending_task_id": state.pending_task_id,
            "pending_actor": state.pending_actor,
            "pending_status": state.pending_status,
            "pending_summary": state.pending_summary,
            "last_transition_key": state.last_transition_key,
            "transition_keys": state.transition_keys,
            "no_progress_turns": state.no_progress_turns,
            "recovery_count": state.recovery_count,
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
