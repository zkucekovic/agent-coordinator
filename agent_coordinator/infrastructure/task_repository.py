"""JsonTaskRepository — persists tasks in a tasks.json file.

Always uses the canonical {"tasks": [], "version": 1} format.
Normalises old bare-list or missing-version files on first load.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_coordinator.application.task_service import TaskRepository
from agent_coordinator.domain.models import Task, TaskMode, TaskStatus

_CURRENT_VERSION = 1


class JsonTaskRepository(TaskRepository):
    """File-backed task repository. Thread-safe for single-process use."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._tasks: dict[str, Task] = {}
        self._load()

    # ── TaskRepository interface ──────────────────────────────────────────────

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def all(self) -> list[Task]:
        return list(self._tasks.values())

    def save(self, task: Task) -> None:
        """Persist a single updated task."""
        self._tasks[task.id] = task
        self._persist()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        raw = json.loads(self._path.read_text(encoding="utf-8"))

        # Normalise: accept bare list, {"tasks":[...]}, or versioned format
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = raw.get("tasks", [])
        else:
            raise ValueError(f"Unrecognised tasks.json format in {self._path}")

        self._tasks = {}
        for item in items:
            task = Task(
                id=item["id"],
                title=item["title"],
                status=TaskStatus(item["status"]),
                mode=TaskMode(item.get("mode", TaskMode.IMPLEMENTATION.value)),
                description=item.get("description", ""),
                priority=int(item.get("priority", 100)),
                owner=item.get("owner", ""),
                acceptance_criteria=item.get("acceptance_criteria", []),
                constraints=item.get("constraints", []),
                files_to_touch=item.get("files_to_touch", []),
                changed_files=item.get("changed_files", []),
                artifacts=item.get("artifacts", []),
                validation_results=item.get("validation_results", []),
                validation_status=item.get("validation_status", "pending"),
                unresolved_issues=item.get("unresolved_issues", []),
                follow_up_tasks=item.get("follow_up_tasks", []),
                rework_count=item.get("rework_count", 0),
                depends_on=item.get("depends_on", []),
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
            )
            self._tasks[task.id] = task

    def _persist(self) -> None:
        payload = {
            "version": _CURRENT_VERSION,
            "tasks": [self._serialise(t) for t in self._tasks.values()],
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _serialise(task: Task) -> dict:
        return {
            "id": task.id,
            "title": task.title,
            "status": task.status.value,
            "mode": task.mode.value,
            "description": task.description,
            "priority": task.priority,
            "owner": task.owner,
            "acceptance_criteria": task.acceptance_criteria,
            "constraints": task.constraints,
            "files_to_touch": task.files_to_touch,
            "changed_files": task.changed_files,
            "artifacts": task.artifacts,
            "validation_results": task.validation_results,
            "validation_status": task.validation_status,
            "unresolved_issues": task.unresolved_issues,
            "follow_up_tasks": task.follow_up_tasks,
            "rework_count": task.rework_count,
            "depends_on": task.depends_on,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
