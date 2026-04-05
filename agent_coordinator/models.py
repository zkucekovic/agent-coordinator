"""Backwards-compatibility shim — re-exports all domain models from agent_coordinator.domain.models.

New code should import directly from agent_coordinator.domain.models.
"""

# ruff: noqa: F401
from agent_coordinator.domain.models import (
    AgentRole,
    HandoffMessage,
    HandoffStatus,
    NextActor,
    RunResult,
    Task,
    TaskStatus,
    ValidationResult,
)
