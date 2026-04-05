"""Backwards-compatibility shim — re-exports all domain models from src.domain.models.

New code should import directly from src.domain.models.
"""

# ruff: noqa: F401
from src.domain.models import (
    AgentRole,
    HandoffMessage,
    HandoffStatus,
    NextActor,
    RunResult,
    Task,
    TaskStatus,
    ValidationResult,
)
