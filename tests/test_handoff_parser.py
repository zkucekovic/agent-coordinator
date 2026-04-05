"""Tests for src.handoff_parser."""

import unittest
from src.handoff_parser import parse_block, extract_latest
from src.models import AgentRole, HandoffStatus, NextActor, HandoffMessage

VALID_ARCHITECT_BLOCK = """
ROLE: architect
STATUS: continue
NEXT: engineer
TASK_ID: task-001
TITLE: Initialize repository
SUMMARY: Set up the repo structure
ACCEPTANCE:
- Directory tree matches spec
CONSTRAINTS:
- None
FILES_TO_TOUCH:
- README.md
CHANGED_FILES: none
VALIDATION:
- Checked manually
BLOCKERS: none
"""

VALID_ENGINEER_BLOCK = """
ROLE: engineer
STATUS: review_required
NEXT: architect
TASK_ID: task-002
TITLE: Define models
SUMMARY: Created enums and dataclasses
ACCEPTANCE: none
CONSTRAINTS: none
FILES_TO_TOUCH:
- src/models.py
CHANGED_FILES:
- src/models.py
VALIDATION:
- import OK
BLOCKERS: none
"""

MISSING_NEXT_BLOCK = """
ROLE: architect
STATUS: continue
TASK_ID: task-001
TITLE: Init repo
SUMMARY: summary here
"""

INVALID_STATUS_BLOCK = """
ROLE: architect
STATUS: flying_spaghetti
NEXT: engineer
TASK_ID: task-001
TITLE: Init repo
SUMMARY: summary here
"""

INVALID_ROLE_BLOCK = """
ROLE: robot
STATUS: continue
NEXT: engineer
TASK_ID: task-001
TITLE: Init repo
SUMMARY: summary here
"""

MULTI_BLOCK_CONTENT = (
    "---HANDOFF---\n" + VALID_ARCHITECT_BLOCK + "\n---END---\n\n"
    "---HANDOFF---\n" + VALID_ENGINEER_BLOCK + "\n---END---\n"
)

INVALID_THEN_VALID_CONTENT = (
    "---HANDOFF---\n" + MISSING_NEXT_BLOCK + "\n---END---\n\n"
    "---HANDOFF---\n" + VALID_ARCHITECT_BLOCK + "\n---END---\n"
)

SINGLE_VALID_CONTENT = "---HANDOFF---\n" + VALID_ARCHITECT_BLOCK + "\n---END---\n"
NO_BLOCKS_CONTENT = "# just prose\nno blocks here\n"


class TestParseBlock(unittest.TestCase):

    def test_valid_architect_block(self):
        msg, errors = parse_block(VALID_ARCHITECT_BLOCK)
        self.assertIsInstance(msg, HandoffMessage)
        self.assertEqual(errors, [])
        self.assertEqual(msg.role, AgentRole.ARCHITECT)
        self.assertEqual(msg.status, HandoffStatus.CONTINUE)
        self.assertEqual(msg.next, NextActor.ENGINEER)
        self.assertEqual(msg.task_id, "task-001")

    def test_valid_engineer_block(self):
        msg, errors = parse_block(VALID_ENGINEER_BLOCK)
        self.assertIsInstance(msg, HandoffMessage)
        self.assertEqual(errors, [])
        self.assertEqual(msg.role, AgentRole.ENGINEER)
        self.assertEqual(msg.status, HandoffStatus.REVIEW_REQUIRED)
        self.assertEqual(msg.next, NextActor.ARCHITECT)

    def test_missing_next_field(self):
        msg, errors = parse_block(MISSING_NEXT_BLOCK)
        self.assertIsNone(msg)
        self.assertTrue(any("NEXT" in e for e in errors), f"Expected NEXT in errors: {errors}")

    def test_invalid_status_value(self):
        msg, errors = parse_block(INVALID_STATUS_BLOCK)
        self.assertIsNone(msg)
        self.assertTrue(len(errors) > 0)

    def test_invalid_role_value(self):
        msg, errors = parse_block(INVALID_ROLE_BLOCK)
        self.assertIsNone(msg)
        self.assertTrue(len(errors) > 0)


class TestExtractLatest(unittest.TestCase):

    def test_single_valid_block(self):
        msg, errors = extract_latest(SINGLE_VALID_CONTENT)
        self.assertIsInstance(msg, HandoffMessage)
        self.assertEqual(errors, [])
        self.assertEqual(msg.role, AgentRole.ARCHITECT)

    def test_two_valid_blocks_returns_last(self):
        msg, errors = extract_latest(MULTI_BLOCK_CONTENT)
        self.assertIsInstance(msg, HandoffMessage)
        self.assertEqual(errors, [])
        # Last block is engineer
        self.assertEqual(msg.role, AgentRole.ENGINEER)

    def test_no_blocks_returns_none_with_errors(self):
        msg, errors = extract_latest(NO_BLOCKS_CONTENT)
        self.assertIsNone(msg)
        self.assertTrue(len(errors) > 0)

    def test_invalid_then_valid_returns_valid(self):
        msg, errors = extract_latest(INVALID_THEN_VALID_CONTENT)
        self.assertIsInstance(msg, HandoffMessage)
        self.assertEqual(errors, [])
        self.assertEqual(msg.role, AgentRole.ARCHITECT)


if __name__ == '__main__':
    unittest.main()
