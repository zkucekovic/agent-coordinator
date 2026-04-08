"""Workflow router — determines the next agent and detects terminal states.

Pure application logic: operates on HandoffMessage domain entities.
No I/O, no subprocess calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_coordinator.domain.models import HandoffMessage, HandoffStatus

# Statuses that mean the coordinator should stop the loop.
_TERMINAL_STATUSES: frozenset[HandoffStatus] = frozenset(
    {
        HandoffStatus.PLAN_COMPLETE,
        HandoffStatus.BLOCKED,
        HandoffStatus.DONE,
    }
)

# NEXT values that mean no agent should be invoked.
_STOP_NEXT_VALUES: frozenset[str] = frozenset({"none", "done", "human"})


@dataclass(frozen=True)
class RoutingDecision:
    """Result of a routing evaluation."""

    next_actor: str  # agent role name, "human", or "none"
    is_terminal: bool  # True → coordinator should stop
    stop_reason: str | None  # human-readable explanation when is_terminal is True


class WorkflowRouter:
    """
    Determines which agent acts next and whether the workflow should stop.

    Routing rules (in priority order):
    1. Terminal HandoffStatus (plan_complete, needs_human, blocked) → stop
    2. NEXT == "none"  → stop (clean finish)
    3. NEXT == "human" → stop (escalation)
    4. Otherwise       → route to the named agent
    """

    def route(self, message: HandoffMessage) -> RoutingDecision:
        """Evaluate a HandoffMessage and return a RoutingDecision."""
        if message.status in _TERMINAL_STATUSES:
            return RoutingDecision(
                next_actor=message.next,
                is_terminal=True,
                stop_reason=self._terminal_reason(message.status),
            )

        next_actor = message.next.lower().strip()

        if next_actor in ("none", "done"):
            return RoutingDecision(
                next_actor="none",
                is_terminal=True,
                stop_reason="Workflow complete (NEXT: none)",
            )

        if next_actor == "human":
            # Human is not terminal - coordinator will handle it
            return RoutingDecision(
                next_actor="human",
                is_terminal=False,
                stop_reason=None,
            )

        return RoutingDecision(
            next_actor=next_actor,
            is_terminal=False,
            stop_reason=None,
        )

    @staticmethod
    def _terminal_reason(status: HandoffStatus) -> str:
        reasons = {
            HandoffStatus.PLAN_COMPLETE: "Plan complete ✅",
            HandoffStatus.DONE: "Workflow complete ✅",
            HandoffStatus.NEEDS_HUMAN: "Human input required ⚠",
            HandoffStatus.BLOCKED: "Workflow blocked 🛑",
        }
        return reasons.get(status, f"Terminal status: {status.value}")
