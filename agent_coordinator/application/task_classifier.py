"""Task classification helpers for structured coordination state."""

from __future__ import annotations

import re

from agent_coordinator.domain.models import Task, TaskMode

_PLANNING_RE = re.compile(r"\b(plan|planning|spec|specification|architecture|decompose|scope|roadmap)\b", re.I)
_DISCOVERY_RE = re.compile(r"\b(discover|discovery|investigate|research|explore|clarify)\b", re.I)
_VERIFICATION_RE = re.compile(r"\b(test|verify|validation|qa|check|lint|typecheck)\b", re.I)
_REVIEW_RE = re.compile(r"\b(review|approve|inspection|audit)\b", re.I)
_REPAIR_RE = re.compile(r"\b(fix|repair|bug|rework|regression|correct)\b", re.I)


def infer_task_mode(
    title: str,
    description: str = "",
    acceptance_criteria: list[str] | None = None,
    files_to_touch: list[str] | None = None,
) -> TaskMode:
    """Infer a task mode from lightweight task metadata."""
    text = " ".join(
        part
        for part in [
            title,
            description,
            " ".join(acceptance_criteria or []),
            " ".join(files_to_touch or []),
        ]
        if part
    )
    if _DISCOVERY_RE.search(text):
        return TaskMode.DISCOVERY
    if _PLANNING_RE.search(text):
        return TaskMode.PLANNING
    if _VERIFICATION_RE.search(text):
        return TaskMode.VERIFICATION
    if _REVIEW_RE.search(text):
        return TaskMode.REVIEW
    if _REPAIR_RE.search(text):
        return TaskMode.REPAIR
    return TaskMode.IMPLEMENTATION


def expected_outputs_for_mode(mode: TaskMode) -> list[str]:
    """Return a human-readable list of expected outputs for a mode."""
    mapping = {
        TaskMode.DISCOVERY: ["findings", "constraints", "candidate approaches"],
        TaskMode.PLANNING: ["concrete executable tasks", "dependencies", "stop condition"],
        TaskMode.IMPLEMENTATION: ["code/config/test artifacts", "validation results"],
        TaskMode.VERIFICATION: ["commands run", "evidence", "pass/fail results"],
        TaskMode.REVIEW: ["defects", "approval", "rework instructions"],
        TaskMode.REPAIR: ["corrective code changes", "updated validation"],
    }
    return mapping[mode]


def default_agent_for_mode(mode: TaskMode) -> str:
    """Return the default agent role for a task mode."""
    if mode in (TaskMode.IMPLEMENTATION, TaskMode.REPAIR):
        return "developer"
    if mode == TaskMode.VERIFICATION:
        return "qa_engineer"
    return "architect"


def task_has_delivery_artifacts(task: Task) -> bool:
    """Return True when the task has artifact-producing outputs."""
    return bool(task.changed_files or task.artifacts)
