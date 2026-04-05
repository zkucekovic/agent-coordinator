"""Tests for src.domain.lifecycle — validate_transition and is_valid_transition."""

import unittest
from src.domain.lifecycle import (
    STANDARD_TRANSITIONS,
    is_valid_transition,
    validate_transition,
)
from src.domain.models import TaskStatus


class TestIsValidTransition(unittest.TestCase):

    def test_planned_to_ready_for_engineering(self):
        self.assertTrue(is_valid_transition(
            TaskStatus.PLANNED, TaskStatus.READY_FOR_ENGINEERING
        ))

    def test_planned_to_done_is_invalid(self):
        self.assertFalse(is_valid_transition(TaskStatus.PLANNED, TaskStatus.DONE))

    def test_done_has_no_valid_transitions(self):
        for target in TaskStatus:
            self.assertFalse(is_valid_transition(TaskStatus.DONE, target))

    def test_rework_requested_to_in_engineering(self):
        self.assertTrue(is_valid_transition(
            TaskStatus.REWORK_REQUESTED, TaskStatus.IN_ENGINEERING
        ))

    def test_blocked_can_resume(self):
        self.assertTrue(is_valid_transition(
            TaskStatus.BLOCKED, TaskStatus.IN_ENGINEERING
        ))
        self.assertTrue(is_valid_transition(
            TaskStatus.BLOCKED, TaskStatus.READY_FOR_ENGINEERING
        ))

    def test_needs_human_can_resume(self):
        self.assertTrue(is_valid_transition(
            TaskStatus.NEEDS_HUMAN, TaskStatus.IN_ENGINEERING
        ))

    def test_custom_transitions_override_standard(self):
        custom = {TaskStatus.PLANNED: {TaskStatus.DONE}}
        self.assertTrue(is_valid_transition(TaskStatus.PLANNED, TaskStatus.DONE, custom))
        self.assertFalse(is_valid_transition(
            TaskStatus.PLANNED, TaskStatus.READY_FOR_ENGINEERING, custom
        ))


class TestValidateTransition(unittest.TestCase):

    def test_valid_transition_does_not_raise(self):
        validate_transition("t1", TaskStatus.PLANNED, TaskStatus.READY_FOR_ENGINEERING)

    def test_invalid_transition_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            validate_transition("t1", TaskStatus.DONE, TaskStatus.PLANNED)
        self.assertIn("t1", str(ctx.exception))
        self.assertIn("done", str(ctx.exception))

    def test_error_message_includes_both_statuses(self):
        with self.assertRaises(ValueError) as ctx:
            validate_transition("task-99", TaskStatus.IN_ENGINEERING, TaskStatus.PLANNED)
        msg = str(ctx.exception)
        self.assertIn("in_engineering", msg)
        self.assertIn("planned", msg)


if __name__ == "__main__":
    unittest.main()
