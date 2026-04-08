"""Tests for src.infrastructure.handoff_reader (HandoffReader)."""

import os
import tempfile
import unittest
from pathlib import Path

from agent_coordinator.domain.models import HandoffStatus
from agent_coordinator.infrastructure.handoff_reader import HandoffReader

_VALID_BLOCK = """\
---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: engineer
TASK_ID: task-001
TITLE: Initialize project
SUMMARY: Set up the structure.
ACCEPTANCE: none
CONSTRAINTS: none
FILES_TO_TOUCH: none
CHANGED_FILES: none
VALIDATION: none
BLOCKERS: none
---END---
"""

_NO_BLOCKS = "# just prose\nnothing here.\n"


def _write_tmp(content: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, dir=tempfile.gettempdir()) as tmp:
        tmp.write(content)
        tmp.flush()
    return Path(tmp.name)


class TestHandoffReader(unittest.TestCase):
    def test_read_returns_message_for_valid_file(self):
        path = _write_tmp(_VALID_BLOCK)
        reader = HandoffReader(path)
        msg = reader.read()
        os.unlink(path)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.role, "architect")
        self.assertEqual(msg.status, HandoffStatus.CONTINUE)
        self.assertEqual(msg.next, "engineer")

    def test_read_returns_none_for_file_with_no_blocks(self):
        path = _write_tmp(_NO_BLOCKS)
        reader = HandoffReader(path)
        msg = reader.read()
        os.unlink(path)
        self.assertIsNone(msg)

    def test_read_raw_returns_full_text(self):
        path = _write_tmp(_VALID_BLOCK)
        reader = HandoffReader(path)
        raw = reader.read_raw()
        os.unlink(path)
        self.assertIn("---HANDOFF---", raw)
        self.assertIn("---END---", raw)

    def test_read_reflects_file_updates(self):
        path = _write_tmp(_VALID_BLOCK)
        reader = HandoffReader(path)
        # Append a second block with a different status
        with path.open("a") as f:
            f.write(
                _VALID_BLOCK.replace("STATUS: continue", "STATUS: plan_complete").replace(
                    "NEXT: engineer", "NEXT: none"
                )
            )
        msg = reader.read()
        os.unlink(path)
        self.assertEqual(msg.status, HandoffStatus.PLAN_COMPLETE)


if __name__ == "__main__":
    unittest.main()
