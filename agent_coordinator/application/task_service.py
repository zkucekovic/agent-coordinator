"""Task service — use cases for task lifecycle management.

Bridges the domain rules (lifecycle, retry policy) with the task repository.
This is the single place where task state changes happen.
"""

from __future__ import annotations

from agent_coordinator.domain.lifecycle import STANDARD_TRANSITIONS, validate_transition
from agent_coordinator.domain.models import Task, TaskStatus
from agent_coordinator.domain.retry_policy import RetryPolicy


class TaskService:
    """
    Enforces task lifecycle rules and provides task queries.

    The repository and transition table are injected so they can be swapped
    in tests or for projects with custom transition rules.
    """

    def __init__(
        self,
        repository: "TaskRepository",
        transitions: dict[TaskStatus, set[TaskStatus]] | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._repo = repository
        self._transitions = transitions if transitions is not None else STANDARD_TRANSITIONS
        self._retry_policy = retry_policy or RetryPolicy()

    # ── Queries ───────────────────────────────────────────────────────────────

    def get(self, task_id: str) -> Task | None:
        """Return the task with the given id, or None."""
        return self._repo.get(task_id)

    def all(self) -> list[Task]:
        """Return all tasks."""
        return self._repo.all()

    def next_ready_task(self) -> Task | None:
        """
        Return the first task that is ready to be worked on:
        - status is planned or ready_for_engineering (or rework_requested)
        - all tasks listed in depends_on are done

        Returns None if no task is ready.
        """
        done_ids = {t.id for t in self._repo.all() if t.status == TaskStatus.DONE}
        eligible_statuses = {
            TaskStatus.PLANNED,
            TaskStatus.READY_FOR_ENGINEERING,
            TaskStatus.REWORK_REQUESTED,
        }
        for task in self._repo.all():
            if task.status not in eligible_statuses:
                continue
            if all(dep in done_ids for dep in task.depends_on):
                return task
        return None

    def active_engineering_task(self) -> Task | None:
        """Return the task currently in IN_ENGINEERING state, or None."""
        for task in self._repo.all():
            if task.status == TaskStatus.IN_ENGINEERING:
                return task
        return None

    # ── Commands ──────────────────────────────────────────────────────────────

    def update_status(self, task_id: str, new_status: TaskStatus) -> None:
        """
        Transition a task to a new status.

        Raises ValueError if:
        - task not found
        - transition is not in the allowed table
        - concurrency guard: another task is already IN_ENGINEERING
        """
        task = self._require(task_id)
        validate_transition(task_id, task.status, new_status, self._transitions)
        self._check_concurrency(task_id, new_status)
        task.status = new_status
        self._repo.save(task)

    def increment_rework(self, task_id: str) -> TaskStatus:
        """
        Increment the rework counter for a task and apply the retry policy.

        Returns the new TaskStatus:
        - REWORK_REQUESTED if within the limit
        - NEEDS_HUMAN or BLOCKED (depending on policy) if the limit is exceeded
        """
        task = self._require(task_id)
        task.rework_count += 1

        if self._retry_policy.is_exceeded(task.rework_count):
            escalation_status = TaskStatus(self._retry_policy.on_exceed)
            # Temporarily force the transition even if not in standard table
            # by transitioning through REWORK_REQUESTED first if needed.
            if task.status != TaskStatus.READY_FOR_ARCHITECT_REVIEW:
                task.status = TaskStatus.REWORK_REQUESTED
            task.status = escalation_status
            self._repo.save(task)
            return escalation_status

        validate_transition(
            task_id, task.status, TaskStatus.REWORK_REQUESTED, self._transitions
        )
        task.status = TaskStatus.REWORK_REQUESTED
        self._repo.save(task)
        return TaskStatus.REWORK_REQUESTED

    def set_acceptance_criteria(self, task_id: str, criteria: list[str]) -> None:
        """Set acceptance criteria for a task."""
        task = self._require(task_id)
        task.acceptance_criteria = criteria
        self._repo.save(task)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require(self, task_id: str) -> Task:
        task = self._repo.get(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id!r}")
        return task

    def _check_concurrency(self, task_id: str, new_status: TaskStatus) -> None:
        if new_status != TaskStatus.IN_ENGINEERING:
            return
        active = self.active_engineering_task()
        if active is not None and active.id != task_id:
            raise ValueError(
                f"Cannot start {task_id!r}: task {active.id!r} is already in_engineering"
            )


class TaskRepository:
    """
    Abstract interface for task persistence.

    Concrete implementations (e.g. JsonTaskRepository) live in infrastructure/.
    Defined here so application layer depends on the abstraction, not the file system.
    """

    def get(self, task_id: str) -> Task | None:
        raise NotImplementedError

    def all(self) -> list[Task]:
        raise NotImplementedError

    def save(self, task: Task) -> None:
        raise NotImplementedError
