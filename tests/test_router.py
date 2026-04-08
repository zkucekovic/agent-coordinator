"""Tests for src.application.router (WorkflowRouter)."""

import unittest

from agent_coordinator.application.router import WorkflowRouter
from agent_coordinator.domain.models import HandoffMessage, HandoffStatus


def _msg(status: HandoffStatus, next_actor: str = "engineer") -> HandoffMessage:
    return HandoffMessage(
        role="architect",
        status=status,
        next=next_actor,
        task_id="task-001",
        title="t",
        summary="s",
    )


class TestWorkflowRouter(unittest.TestCase):
    def setUp(self):
        self.router = WorkflowRouter()

    # ── Terminal statuses ─────────────────────────────────────────────────────

    def test_plan_complete_is_terminal(self):
        decision = self.router.route(_msg(HandoffStatus.PLAN_COMPLETE, "human"))
        self.assertTrue(decision.is_terminal)
        self.assertIn("complete", decision.stop_reason.lower())

    def test_needs_human_is_not_terminal_when_next_human(self):
        # needs_human + NEXT: human is handled by coordinator
        decision = self.router.route(_msg(HandoffStatus.NEEDS_HUMAN, "human"))
        self.assertFalse(decision.is_terminal)
        self.assertEqual(decision.next_actor, "human")

    def test_blocked_status_is_terminal(self):
        decision = self.router.route(_msg(HandoffStatus.BLOCKED, "architect"))
        self.assertTrue(decision.is_terminal)

    # ── NEXT sentinel values ──────────────────────────────────────────────────

    def test_next_none_is_terminal(self):
        decision = self.router.route(_msg(HandoffStatus.CONTINUE, "none"))
        self.assertTrue(decision.is_terminal)
        self.assertEqual(decision.next_actor, "none")

    def test_next_human_is_not_terminal(self):
        # Human is handled by coordinator, not terminal
        decision = self.router.route(_msg(HandoffStatus.CONTINUE, "human"))
        self.assertFalse(decision.is_terminal)
        self.assertEqual(decision.next_actor, "human")

    # ── Normal routing ────────────────────────────────────────────────────────

    def test_continue_to_engineer_is_not_terminal(self):
        decision = self.router.route(_msg(HandoffStatus.CONTINUE, "engineer"))
        self.assertFalse(decision.is_terminal)
        self.assertEqual(decision.next_actor, "engineer")
        self.assertIsNone(decision.stop_reason)

    def test_review_required_to_architect_is_not_terminal(self):
        decision = self.router.route(_msg(HandoffStatus.REVIEW_REQUIRED, "architect"))
        self.assertFalse(decision.is_terminal)
        self.assertEqual(decision.next_actor, "architect")

    def test_custom_role_routes_correctly(self):
        decision = self.router.route(_msg(HandoffStatus.CONTINUE, "qa"))
        self.assertFalse(decision.is_terminal)
        self.assertEqual(decision.next_actor, "qa")

    def test_next_actor_is_lowercased(self):
        decision = self.router.route(_msg(HandoffStatus.CONTINUE, "  ENGINEER  "))
        self.assertEqual(decision.next_actor, "engineer")


if __name__ == "__main__":
    unittest.main()
