"""Task service — use cases for task lifecycle management.

Bridges the domain rules (lifecycle, retry policy) with the task repository.
This is the single place where task state changes happen.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent_coordinator.application.task_classifier import default_agent_for_mode, infer_task_mode
from agent_coordinator.domain.lifecycle import STANDARD_TRANSITIONS, validate_transition
from agent_coordinator.domain.models import Task, TaskMode, TaskStatus
from agent_coordinator.domain.retry_policy import RetryPolicy


class TaskService:
    """
    Enforces task lifecycle rules and provides task queries.

    The repository and transition table are injected so they can be swapped
    in tests or for projects with custom transition rules.
    """

    def __init__(
        self,
        repository: TaskRepository,
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
        tasks = self._repo.all()
        changed = False
        for task in tasks:
            if not isinstance(task.mode, TaskMode):
                task.mode = infer_task_mode(
                    task.title,
                    task.description,
                    task.acceptance_criteria,
                    task.files_to_touch,
                )
                changed = True
        if changed:
            for task in tasks:
                self._repo.save(task)
        return tasks

    def next_ready_task(self) -> Task | None:
        """
        Return the first task that is ready to be worked on:
        - status is planned or ready_for_engineering (or rework_requested)
        - all tasks listed in depends_on are done

        Returns None if no task is ready.
        """
        ready = self.ready_queue()
        return ready[0] if ready else None

    def ready_queue(self) -> list[Task]:
        """Return ready tasks sorted by scheduling priority."""
        tasks = self.all()
        done_ids = {t.id for t in tasks if t.status == TaskStatus.DONE}
        planning_sufficient = self.planning_is_sufficient(tasks)
        eligible_statuses = {
            TaskStatus.PLANNED,
            TaskStatus.READY_FOR_ENGINEERING,
            TaskStatus.REWORK_REQUESTED,
            TaskStatus.READY_FOR_ARCHITECT_REVIEW,
        }
        ready: list[Task] = []
        for task in tasks:
            if task.status not in eligible_statuses:
                continue
            if task.mode == TaskMode.VERIFICATION and not task.changed_files:
                continue
            if all(dep in done_ids for dep in task.depends_on):
                ready.append(task)
        return sorted(ready, key=lambda task: self._scheduler_key(task, planning_sufficient))

    def planning_is_sufficient(self, tasks: list[Task] | None = None) -> bool:
        """Return True when execution should be preferred over more planning."""
        tasks = tasks if tasks is not None else self.all()
        for task in tasks:
            if task.mode not in (TaskMode.IMPLEMENTATION, TaskMode.REPAIR):
                continue
            if task.status not in {
                TaskStatus.PLANNED,
                TaskStatus.READY_FOR_ENGINEERING,
                TaskStatus.REWORK_REQUESTED,
            }:
                continue
            if task.description or task.acceptance_criteria or task.files_to_touch:
                return True
        return False

    def default_agent_for_task(self, task: Task) -> str:
        """Return the default agent role for a task."""
        return default_agent_for_mode(task.mode)

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
        task.updated_at = datetime.now(timezone.utc).isoformat()
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

        validate_transition(task_id, task.status, TaskStatus.REWORK_REQUESTED, self._transitions)
        task.status = TaskStatus.REWORK_REQUESTED
        self._repo.save(task)
        return TaskStatus.REWORK_REQUESTED

    def set_acceptance_criteria(self, task_id: str, criteria: list[str]) -> None:
        """Set acceptance criteria for a task."""
        task = self._require(task_id)
        task.acceptance_criteria = criteria
        self._repo.save(task)

    def save(self, task: Task) -> None:
        """Persist a mutated task."""
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self._repo.save(task)

    def ensure_task(
        self,
        task_id: str,
        title: str,
        *,
        mode: TaskMode | None = None,
        description: str = "",
    ) -> Task:
        """Return an existing task or create a minimal new one."""
        task = self.get(task_id)
        if task is not None:
            return task
        now = datetime.now(timezone.utc).isoformat()
        task = Task(
            id=task_id,
            title=title,
            status=TaskStatus.PLANNED,
            mode=mode or infer_task_mode(title, description),
            description=description,
            created_at=now,
            updated_at=now,
        )
        self._repo.save(task)
        return task

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
            raise ValueError(f"Cannot start {task_id!r}: task {active.id!r} is already in_engineering")

    @staticmethod
    def _scheduler_key(task: Task, planning_sufficient: bool) -> tuple[int, int, str, str]:
        mode_order = {
            TaskMode.IMPLEMENTATION: 0,
            TaskMode.REPAIR: 1,
            TaskMode.VERIFICATION: 2,
            TaskMode.REVIEW: 3,
            TaskMode.DISCOVERY: 4,
            TaskMode.PLANNING: 5,
        }
        if not planning_sufficient and task.mode in (TaskMode.DISCOVERY, TaskMode.PLANNING):
            mode_rank = -1
        else:
            mode_rank = mode_order[task.mode]
        return (mode_rank, task.priority, task.created_at or "", task.id)


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
