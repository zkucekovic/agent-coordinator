"""Persistent task store for the two-agent coordination workflow."""

import json
from pathlib import Path
from src.models import Task, TaskStatus

# Valid task state transitions: {from_status: {allowed_to_statuses}}
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PLANNED: {
        TaskStatus.READY_FOR_ENGINEERING,
        TaskStatus.IN_ENGINEERING,
        TaskStatus.BLOCKED,
    },
    TaskStatus.READY_FOR_ENGINEERING: {
        TaskStatus.IN_ENGINEERING,
        TaskStatus.BLOCKED,
    },
    TaskStatus.IN_ENGINEERING: {
        TaskStatus.READY_FOR_ARCHITECT_REVIEW,
        TaskStatus.REWORK_REQUESTED,
        TaskStatus.BLOCKED,
    },
    TaskStatus.READY_FOR_ARCHITECT_REVIEW: {
        TaskStatus.DONE,
        TaskStatus.REWORK_REQUESTED,
        TaskStatus.BLOCKED,
    },
    TaskStatus.REWORK_REQUESTED: {
        TaskStatus.IN_ENGINEERING,
        TaskStatus.BLOCKED,
    },
    TaskStatus.DONE: set(),  # terminal — no further transitions
    TaskStatus.BLOCKED: {
        TaskStatus.IN_ENGINEERING,
        TaskStatus.READY_FOR_ENGINEERING,
    },
}


class TaskStore:
    """Loads, queries, updates, and persists tasks from a JSON file."""

    def __init__(self, filepath: str) -> None:
        self._path = Path(filepath)
        self._tasks: dict[str, Task] = {}
        self._load()

    def _load(self) -> None:
        """Load tasks from the JSON file."""
        with open(self._path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Support both a bare list and {"tasks": [...]} formats
        items = data['tasks'] if isinstance(data, dict) and 'tasks' in data else data
        self._tasks = {}
        for item in items:
            task = Task(
                id=item['id'],
                title=item['title'],
                status=TaskStatus(item['status']),
                acceptance_criteria=item.get('acceptance_criteria', []),
            )
            self._tasks[task.id] = task

    def _save(self) -> None:
        """Persist current tasks to the JSON file."""
        items = [
            {
                'id': t.id,
                'title': t.title,
                'status': t.status.value,
                'acceptance_criteria': t.acceptance_criteria,
            }
            for t in self._tasks.values()
        ]
        # Preserve the {"tasks": [...]} wrapper when the original file used it
        with open(self._path, 'r', encoding='utf-8') as f:
            original = json.load(f)
        if isinstance(original, dict) and 'tasks' in original:
            payload = {**original, 'tasks': items}
        else:
            payload = items
        with open(self._path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)

    def get(self, task_id: str) -> Task | None:
        """Return the Task with the given id, or None if not found."""
        return self._tasks.get(task_id)

    def all(self) -> list[Task]:
        """Return all tasks as a list."""
        return list(self._tasks.values())

    def active_engineering_task(self) -> Task | None:
        """Return the task currently in IN_ENGINEERING state, or None."""
        for task in self._tasks.values():
            if task.status == TaskStatus.IN_ENGINEERING:
                return task
        return None

    def update_status(self, task_id: str, new_status: TaskStatus) -> None:
        """
        Update a task's status with lifecycle validation and persist.
        Raises ValueError if task not found, transition is invalid,
        or concurrency guard is violated.
        """
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id!r}")

        allowed = VALID_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {task.status.value} → {new_status.value}"
            )

        # Concurrency guard: only one task in IN_ENGINEERING at a time
        if new_status == TaskStatus.IN_ENGINEERING:
            active = self.active_engineering_task()
            if active is not None and active.id != task_id:
                raise ValueError(
                    f"Another task is already in_engineering: {active.id!r}"
                )

        task.status = new_status
        self._save()

    def set_acceptance_criteria(self, task_id: str, criteria: list[str]) -> None:
        """Set acceptance criteria for a task and persist. Raises ValueError if not found."""
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id!r}")
        task.acceptance_criteria = criteria
        self._save()
