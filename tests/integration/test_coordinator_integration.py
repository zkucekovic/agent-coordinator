"""
Integration tests for the coordinator loop — real two-agent OpenCode sessions.

Requires: RUN_INTEGRATION_TESTS=1

Tests:
  1. Single engineer turn: architect seeds handoff.md → engineer runs →
     handoff.md gains a new valid block and event log is written.
  2. Full two-turn cycle: architect → engineer → architect, verifying
     both agents follow the handoff protocol end-to-end.

The test workspace uses minimal prompts that are extremely prescriptive
about the expected handoff block format to reduce LLM variance.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.integration.conftest import requires_integration
from agent_coordinator.infrastructure.handoff_reader import HandoffReader
from agent_coordinator.domain.models import HandoffStatus

# ── Workspace fixtures ────────────────────────────────────────────────────────

_SHARED_RULES = """\
# Shared Rules

1. Always read `handoff.md` before acting.
2. Always end your turn by appending a valid `---HANDOFF---` … `---END---` block.
3. Never remove or modify existing blocks — only append.
4. Use the exact field names shown in the template.
"""

_ARCHITECT_PROMPT = """\
# Architect Agent

You review engineer work and assign tasks.

## Your task this turn

1. Read the latest `---HANDOFF---` block in `handoff.md` using a file-read tool.
2. Check that `int_test_result.txt` exists and contains `integration_ok`.
3. **Use a file-write tool to APPEND** the block below to `handoff.md`.
   Do NOT just output it in text — you MUST write it to the file with a tool call.

## Exact block to append (write it verbatim, changing only SUMMARY):

```
---HANDOFF---
ROLE: architect
STATUS: approved
NEXT: none
TASK_ID: int-001
TITLE: Create integration test file
SUMMARY: Verified int_test_result.txt exists with content 'integration_ok'
ACCEPTANCE:
- int_test_result.txt exists with content 'integration_ok' - VERIFIED
CONSTRAINTS:
- only the specified file was created
FILES_TO_TOUCH:
- int_test_result.txt
CHANGED_FILES:
- n/a
VALIDATION:
- file verified
BLOCKERS:
- none
---END---
```

IMPORTANT: Use your file-write/edit tool to append that block to handoff.md.
Do not skip the file write — the block must appear in the file, not only in chat.
"""

_ENGINEER_PROMPT = """\
# Engineer Agent

You implement tasks assigned by the architect.

## Your task this turn

1. Read the latest `---HANDOFF---` block in `handoff.md`.
2. Implement the task: create a file called `int_test_result.txt`
   in your working directory with content `integration_ok`.
3. Append the following block VERBATIM to `handoff.md` (replace nothing else):

```
---HANDOFF---
ROLE: developer
STATUS: review_required
NEXT: architect
TASK_ID: int-001
TITLE: Create integration test file
SUMMARY: Created int_test_result.txt with content 'integration_ok'
ACCEPTANCE:
- int_test_result.txt exists - PASS
CONSTRAINTS:
- Only the specified file was created
FILES_TO_TOUCH:
- int_test_result.txt
CHANGED_FILES:
- int_test_result.txt
VALIDATION:
- File was created and contains 'integration_ok'
BLOCKERS:
- none
---END---
```

Append that block EXACTLY as shown. Do not change the field names or values.
"""

_INITIAL_ARCHITECT_BLOCK = """\
---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: engineer
TASK_ID: int-001
TITLE: Create integration test file
SUMMARY: Create int_test_result.txt with content 'integration_ok' to verify the coordination pipeline.
ACCEPTANCE:
- int_test_result.txt exists with content 'integration_ok'
CONSTRAINTS:
- Only create the one specified file
FILES_TO_TOUCH:
- int_test_result.txt
CHANGED_FILES:
- n/a
VALIDATION:
- n/a
BLOCKERS:
- none
---END---
"""

_AGENTS_JSON = {
    "agents": {
        "architect": {
            "model": None,
            "prompt_file": "prompts/architect.md",
        },
        "developer": {
            "model": None,
            "prompt_file": "prompts/developer.md",
        },
    }
}


# ── Workspace builder ─────────────────────────────────────────────────────────

def _build_workspace() -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="coord_inttest_"))
    prompts = workspace / "prompts"
    prompts.mkdir()

    (workspace / "handoff.md").write_text(_INITIAL_ARCHITECT_BLOCK)
    (workspace / "agents.json").write_text(json.dumps(_AGENTS_JSON, indent=2))
    (prompts / "shared_rules.md").write_text(_SHARED_RULES)
    (prompts / "architect.md").write_text(_ARCHITECT_PROMPT)
    (prompts / "developer.md").write_text(_ENGINEER_PROMPT)

    return workspace


def _count_handoff_blocks(path: Path) -> int:
    """Count how many ---HANDOFF--- blocks are in a file."""
    return path.read_text().count("---HANDOFF---")


# ── Tests ─────────────────────────────────────────────────────────────────────

@requires_integration
class TestCoordinatorSingleEngineerTurn(unittest.TestCase):
    """One-turn test: engineer receives the architect seed block and responds."""

    def setUp(self):
        self._workspace = _build_workspace()

    def tearDown(self):
        shutil.rmtree(self._workspace, ignore_errors=True)

    def _run(self, max_turns: int = 1) -> None:
        from agent_coordinator.cli import run_coordinator
        run_coordinator(
            workspace=self._workspace,
            max_turns=max_turns,
            reset=False,
            verbose=True,
        )

    def test_engineer_appends_handoff_block(self):
        """After one engineer turn, handoff.md must contain 2 blocks."""
        blocks_before = _count_handoff_blocks(self._workspace / "handoff.md")
        self.assertEqual(blocks_before, 1, "Pre-condition: one seed block")

        self._run(max_turns=1)

        blocks_after = _count_handoff_blocks(self._workspace / "handoff.md")
        self.assertEqual(blocks_after, 2, "Engineer must append exactly one block")

    def test_engineer_block_has_correct_role(self):
        """The appended block must have ROLE: developer."""
        self._run(max_turns=1)
        reader = HandoffReader(self._workspace / "handoff.md")
        msg = reader.read()
        self.assertIsNotNone(msg, "HandoffReader must parse the latest block")
        self.assertEqual(msg.role, "developer")

    def test_engineer_block_has_valid_status(self):
        """The engineer block must carry a recognised status value."""
        self._run(max_turns=1)
        reader = HandoffReader(self._workspace / "handoff.md")
        msg = reader.read()
        valid_statuses = {
            HandoffStatus.REVIEW_REQUIRED,
            HandoffStatus.BLOCKED,
            HandoffStatus.NEEDS_HUMAN,
        }
        self.assertIn(
            msg.status, valid_statuses,
            f"Expected an engineer-appropriate status, got {msg.status!r}",
        )

    def test_event_log_written_after_turn(self):
        """The event log must have one entry after one coordinator turn."""
        self._run(max_turns=1)
        log_path = self._workspace / "workflow_events.jsonl"
        self.assertTrue(log_path.exists(), "workflow_events.jsonl must be created")
        entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        self.assertEqual(len(entries), 1, "Expected exactly one event log entry")
        entry = entries[0]
        self.assertEqual(entry["agent"], "developer")
        self.assertEqual(entry["turn"], 1)

    def test_session_file_created(self):
        """SessionStore must persist the engineer's session_id to disk."""
        self._run(max_turns=1)
        session_file = self._workspace / ".coordinator_sessions.json"
        self.assertTrue(session_file.exists(), "Session file must be created")
        data = json.loads(session_file.read_text())
        self.assertIn("developer", data, "Session file must contain 'engineer' key")
        self.assertTrue(len(data["developer"]) > 0)

    def test_int_test_result_file_created(self):
        """The engineer must have created int_test_result.txt in the workspace."""
        self._run(max_turns=1)
        result_file = self._workspace / "int_test_result.txt"
        self.assertTrue(
            result_file.exists(),
            "Engineer must create int_test_result.txt as instructed",
        )
        self.assertIn("integration_ok", result_file.read_text())


@requires_integration
class TestCoordinatorTwoTurnCycle(unittest.TestCase):
    """
    Full architect → engineer → architect cycle.

    After 2 turns:
    - handoff.md has 3 blocks (seed + engineer + architect)
    - event log has 2 entries
    - the second architect block carries a valid status
    """

    def setUp(self):
        self._workspace = _build_workspace()

    def tearDown(self):
        shutil.rmtree(self._workspace, ignore_errors=True)

    def _run(self) -> None:
        from agent_coordinator.cli import run_coordinator
        run_coordinator(
            workspace=self._workspace,
            max_turns=2,
            reset=False,
            verbose=True,
        )

    def test_two_turns_produce_three_blocks(self):
        """handoff.md must have at least 3 blocks after the two-turn cycle.

        We assert >= 3 (not exactly 3) because a model may occasionally
        echo the handoff block in prose before its tool-call write, which
        can result in an extra block being appended.
        """
        self._run()
        blocks = _count_handoff_blocks(self._workspace / "handoff.md")
        self.assertGreaterEqual(blocks, 3, f"Expected ≥3 blocks, found {blocks}")

    def test_event_log_has_two_entries(self):
        """Event log must record both turns.

        If only 1 entry exists it means the architect ran but didn't write
        to handoff.md — a real protocol failure worth flagging.
        """
        self._run()
        log_path = self._workspace / "workflow_events.jsonl"
        self.assertTrue(log_path.exists())
        entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        self.assertEqual(len(entries), 2, f"Expected 2 log entries, found {len(entries)}")

    def test_first_event_is_engineer_turn(self):
        """The first event log entry should record the engineer's turn."""
        self._run()
        log_path = self._workspace / "workflow_events.jsonl"
        entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        self.assertGreaterEqual(len(entries), 1, "Expected at least one event log entry")
        self.assertEqual(entries[0]["agent"], "developer")

    def test_second_event_is_architect_turn(self):
        """The second event log entry should record the architect's turn.

        Skipped if the coordinator broke early because the architect did not
        write to handoff.md (that failure is caught by test_event_log_has_two_entries).
        """
        self._run()
        log_path = self._workspace / "workflow_events.jsonl"
        entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        if len(entries) < 2:
            self.skipTest("Architect did not write to handoff.md (loop broke early)")
        self.assertEqual(entries[1]["agent"], "architect")

    def test_final_block_is_architect_role(self):
        """The last block in handoff.md must be from the architect.

        If the coordinator detected that the architect did not write to the
        file (loop broke with a warning after the engineer's turn), this
        assertion is skipped — the failure is caught by test_event_log_has_two_entries.
        """
        self._run()
        log_path = self._workspace / "workflow_events.jsonl"
        entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
        if len(entries) < 2:
            self.skipTest("Architect did not write to handoff.md (loop broke early); "
                          "covered by test_event_log_has_two_entries")
        reader = HandoffReader(self._workspace / "handoff.md")
        msg = reader.read()
        self.assertEqual(msg.role, "architect")

    def test_both_agents_have_session_ids(self):
        """Both agents must have persisted session IDs in the session file."""
        self._run()
        session_file = self._workspace / ".coordinator_sessions.json"
        self.assertTrue(session_file.exists())
        data = json.loads(session_file.read_text())
        self.assertIn("developer", data)
        self.assertIn("architect", data)
        self.assertTrue(len(data["developer"]) > 0)
        self.assertTrue(len(data["architect"]) > 0)

    def test_final_architect_block_has_valid_status(self):
        """The architect must write a recognised status on review.

        Skipped if the coordinator broke early (architect turn produced no file write).
        """
        self._run()
        log_path = self._workspace / "workflow_events.jsonl"
        entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
        if len(entries) < 2:
            self.skipTest("Architect did not write to handoff.md (loop broke early); "
                          "covered by test_event_log_has_two_entries")
        reader = HandoffReader(self._workspace / "handoff.md")
        msg = reader.read()
        valid_statuses = {
            HandoffStatus.CONTINUE,
            HandoffStatus.APPROVED,
            HandoffStatus.REWORK_REQUIRED,
            HandoffStatus.PLAN_COMPLETE,
            HandoffStatus.BLOCKED,
            HandoffStatus.NEEDS_HUMAN,
        }
        self.assertIn(
            msg.status, valid_statuses,
            f"Architect wrote unrecognised status: {msg.status!r}",
        )


if __name__ == "__main__":
    unittest.main()
