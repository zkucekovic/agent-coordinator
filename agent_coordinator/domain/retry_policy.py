"""Retry policy — defines how many rework cycles are allowed before escalation.

Pure domain concept: no I/O, no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

_ON_EXCEED_VALUES = ("needs_human", "blocked")


@dataclass(frozen=True)
class RetryPolicy:
    """
    Governs how many times a task may be sent back for rework.

    Attributes:
        max_rework:  Maximum number of rework cycles allowed (0 = unlimited).
        on_exceed:   What happens when the limit is hit.
                     "needs_human" — escalate to human operator.
                     "blocked"     — mark the task as blocked.
    """

    max_rework: int = 3
    on_exceed: str = "needs_human"

    def __post_init__(self) -> None:
        if self.max_rework < 0:
            raise ValueError(f"max_rework must be >= 0, got {self.max_rework}")
        if self.on_exceed not in _ON_EXCEED_VALUES:
            raise ValueError(f"on_exceed must be one of {_ON_EXCEED_VALUES}, got {self.on_exceed!r}")

    def is_exceeded(self, rework_count: int) -> bool:
        """Return True if rework_count has hit or passed the limit."""
        return self.max_rework > 0 and rework_count >= self.max_rework

    @classmethod
    def unlimited(cls) -> RetryPolicy:
        """Return a policy that never escalates (max_rework=0)."""
        return cls(max_rework=0, on_exceed="needs_human")

    @classmethod
    def from_dict(cls, data: dict) -> RetryPolicy:
        """Construct from a plain dict (e.g. loaded from agents.json)."""
        return cls(
            max_rework=int(data.get("max_rework", 3)),
            on_exceed=str(data.get("on_exceed", "needs_human")),
        )
