"""Domain entities for the multi-agent coordination system.

These are plain data structures with no I/O or external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class RunResult:
    """Result of a single agent turn, returned by any AgentRunner implementation."""
    session_id: str
    text: str


class TaskStatus(Enum):
    PLANNED = "planned"
    READY_FOR_ENGINEERING = "ready_for_engineering"
    IN_ENGINEERING = "in_engineering"
    READY_FOR_ARCHITECT_REVIEW = "ready_for_architect_review"
    REWORK_REQUESTED = "rework_requested"
    DONE = "done"
    BLOCKED = "blocked"
    NEEDS_HUMAN = "needs_human"   # retry limit exceeded; human must intervene


class HandoffStatus(Enum):
    CONTINUE = "continue"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    NEEDS_HUMAN = "needs_human"
    PLAN_COMPLETE = "plan_complete"
    IMPLEMENTATION_COMPLETE = "implementation_complete"
    REWORK_REQUIRED = "rework_required"
    APPROVED = "approved"
    DONE = "done"


class AgentRole(Enum):
    """Built-in role constants. Custom roles are plain strings — any value is valid."""
    ARCHITECT = "architect"
    ENGINEER = "engineer"


class NextActor(Enum):
    """Sentinel values for routing. Agents can also route to custom role names."""
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
    rework_count: int = 0
    depends_on: list[str] = field(default_factory=list)
    created_at: str = ""  # ISO 8601 timestamp
    updated_at: str = ""  # ISO 8601 timestamp


@dataclass
class HandoffMessage:
    role: str           # any agent role name (e.g. "architect", "qa", "frontend")
    status: HandoffStatus
    next: str           # any agent role name, or "human" / "none"
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
