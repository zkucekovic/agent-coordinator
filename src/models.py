"""Workflow models and enums for the two-agent coordination system."""

from enum import Enum
from dataclasses import dataclass, field


class AgentRole(Enum):
    ARCHITECT = "architect"
    ENGINEER = "engineer"


class TaskStatus(Enum):
    PLANNED = "planned"
    READY_FOR_ENGINEERING = "ready_for_engineering"
    IN_ENGINEERING = "in_engineering"
    READY_FOR_ARCHITECT_REVIEW = "ready_for_architect_review"
    REWORK_REQUESTED = "rework_requested"
    DONE = "done"
    BLOCKED = "blocked"


class HandoffStatus(Enum):
    CONTINUE = "continue"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    NEEDS_HUMAN = "needs_human"
    PLAN_COMPLETE = "plan_complete"
    IMPLEMENTATION_COMPLETE = "implementation_complete"
    REWORK_REQUIRED = "rework_required"
    APPROVED = "approved"


class NextActor(Enum):
    ARCHITECT = "architect"
    ENGINEER = "engineer"
    HUMAN = "human"
    NONE = "none"


@dataclass
class Task:
    id: str
    title: str
    status: TaskStatus
    acceptance_criteria: list[str] = field(default_factory=list)


@dataclass
class HandoffMessage:
    role: AgentRole
    status: HandoffStatus
    next: NextActor
    task_id: str
    title: str
    summary: str
    acceptance: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    files_to_touch: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    validation: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
