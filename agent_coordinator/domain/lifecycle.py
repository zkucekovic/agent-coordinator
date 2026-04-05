"""Task lifecycle rules — valid state transitions and transition validation.

This module is pure business logic: no I/O, no external dependencies.
The transition map can be injected where needed to support custom policies.
"""

from __future__ import annotations

from agent_coordinator.domain.models import TaskStatus


# Standard transition map: {from_status: {allowed_to_statuses}}
STANDARD_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
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
        TaskStatus.NEEDS_HUMAN,
    },
    TaskStatus.READY_FOR_ARCHITECT_REVIEW: {
        TaskStatus.DONE,
        TaskStatus.REWORK_REQUESTED,
        TaskStatus.BLOCKED,
        TaskStatus.NEEDS_HUMAN,
    },
    TaskStatus.REWORK_REQUESTED: {
        TaskStatus.IN_ENGINEERING,
        TaskStatus.BLOCKED,
        TaskStatus.NEEDS_HUMAN,
    },
    TaskStatus.DONE: set(),  # terminal — no further transitions
    TaskStatus.BLOCKED: {
        TaskStatus.IN_ENGINEERING,
        TaskStatus.READY_FOR_ENGINEERING,
    },
    TaskStatus.NEEDS_HUMAN: {
        TaskStatus.IN_ENGINEERING,
        TaskStatus.READY_FOR_ENGINEERING,
    },
}


def is_valid_transition(
    from_status: TaskStatus,
    to_status: TaskStatus,
    transitions: dict[TaskStatus, set[TaskStatus]] | None = None,
) -> bool:
    """Return True if transitioning from_status → to_status is permitted."""
    table = transitions if transitions is not None else STANDARD_TRANSITIONS
    return to_status in table.get(from_status, set())


def validate_transition(
    task_id: str,
    from_status: TaskStatus,
    to_status: TaskStatus,
    transitions: dict[TaskStatus, set[TaskStatus]] | None = None,
) -> None:
    """Raise ValueError if the transition is not permitted."""
    if not is_valid_transition(from_status, to_status, transitions):
        raise ValueError(
            f"Invalid transition for task {task_id!r}: "
            f"{from_status.value} → {to_status.value}"
        )
