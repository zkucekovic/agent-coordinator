"""Backwards-compatibility shim — delegates to TaskService + JsonTaskRepository.

New code should use TaskService directly.
"""

from pathlib import Path

from src.application.task_service import TaskService
from src.domain.lifecycle import STANDARD_TRANSITIONS
from src.domain.models import Task, TaskStatus
from src.infrastructure.task_repository import JsonTaskRepository

# Re-export for consumers that import VALID_TRANSITIONS from task_store
VALID_TRANSITIONS = STANDARD_TRANSITIONS


class TaskStore:
    """Deprecated façade kept for backwards compatibility. Use TaskService instead."""

    def __init__(self, filepath: str) -> None:
        repo = JsonTaskRepository(Path(filepath))
        self._service = TaskService(repo)

    def get(self, task_id: str) -> Task | None:
        return self._service.get(task_id)

    def all(self) -> list[Task]:
        return self._service.all()

    def active_engineering_task(self) -> Task | None:
        return self._service.active_engineering_task()

    def update_status(self, task_id: str, new_status: TaskStatus) -> None:
        self._service.update_status(task_id, new_status)

    def set_acceptance_criteria(self, task_id: str, criteria: list[str]) -> None:
        self._service.set_acceptance_criteria(task_id, criteria)

