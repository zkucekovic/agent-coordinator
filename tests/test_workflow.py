"""Tests for src.workflow helper functions."""

import os
import tempfile
import unittest

from agent_coordinator.models import HandoffMessage, HandoffStatus
from agent_coordinator.workflow import (
    get_next_actor,
    get_workflow_state,
    is_blocked,
    is_human_escalation,
    is_plan_complete,
)

VALID_BLOCK_CONTENT = """\
---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: engineer
TASK_ID: task-001
TITLE: Init repo
SUMMARY: Set up the structure
ACCEPTANCE: none
CONSTRAINTS: none
FILES_TO_TOUCH: none
CHANGED_FILES: none
VALIDATION: none
BLOCKERS: none
---END---
"""


def _make_msg(status=HandoffStatus.CONTINUE, next_actor="engineer"):
    return HandoffMessage(
        role="architect",
        status=status,
        next=next_actor,
        task_id="t",
        title="t",
        summary="s",
    )


class TestGetNextActor(unittest.TestCase):
    def test_returns_msg_next(self):
        msg = _make_msg(next_actor="engineer")
        self.assertEqual(get_next_actor(msg), "engineer")

    def test_returns_human(self):
        msg = _make_msg(next_actor="human")
        self.assertEqual(get_next_actor(msg), "human")

    def test_returns_custom_role(self):
        msg = _make_msg(next_actor="qa")
        self.assertEqual(get_next_actor(msg), "qa")


class TestIsPlanComplete(unittest.TestCase):
    def test_true_for_plan_complete(self):
        msg = _make_msg(status=HandoffStatus.PLAN_COMPLETE)
        self.assertTrue(is_plan_complete(msg))

    def test_false_for_continue(self):
        msg = _make_msg(status=HandoffStatus.CONTINUE)
        self.assertFalse(is_plan_complete(msg))

    def test_false_for_approved(self):
        msg = _make_msg(status=HandoffStatus.APPROVED)
        self.assertFalse(is_plan_complete(msg))


class TestIsHumanEscalation(unittest.TestCase):
    def test_true_when_next_is_human(self):
        msg = _make_msg(next_actor="human")
        self.assertTrue(is_human_escalation(msg))

    def test_false_when_next_is_engineer(self):
        msg = _make_msg(next_actor="engineer")
        self.assertFalse(is_human_escalation(msg))

    def test_false_when_next_is_none(self):
        msg = _make_msg(next_actor="none")
        self.assertFalse(is_human_escalation(msg))


class TestIsBlocked(unittest.TestCase):
    def test_true_for_blocked_status(self):
        msg = _make_msg(status=HandoffStatus.BLOCKED)
        self.assertTrue(is_blocked(msg))

    def test_true_for_needs_human_status(self):
        msg = _make_msg(status=HandoffStatus.NEEDS_HUMAN)
        self.assertTrue(is_blocked(msg))

    def test_false_for_continue(self):
        msg = _make_msg(status=HandoffStatus.CONTINUE)
        self.assertFalse(is_blocked(msg))


class TestGetWorkflowState(unittest.TestCase):
    def setUp(self):
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, dir=tests_dir) as valid_tf:
            valid_tf.write(VALID_BLOCK_CONTENT)
            valid_tf.flush()
        self._valid_tf_name = valid_tf.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, dir=tests_dir) as empty_tf:
            empty_tf.write("# no blocks here\n")
            empty_tf.flush()
        self._empty_tf_name = empty_tf.name

    def tearDown(self):
        os.unlink(self._valid_tf_name)
        os.unlink(self._empty_tf_name)

    def test_valid_block_returns_valid_true(self):
        state = get_workflow_state(self._valid_tf_name)
        self.assertTrue(state["valid"])
        self.assertEqual(state["next_actor"], "engineer")
        self.assertEqual(state["status"], "continue")
        self.assertEqual(state["task_id"], "task-001")
        self.assertEqual(state["errors"], [])

    def test_no_blocks_returns_valid_false(self):
        state = get_workflow_state(self._empty_tf_name)
        self.assertFalse(state["valid"])
        self.assertTrue(len(state["errors"]) > 0)


if __name__ == "__main__":
    unittest.main()
