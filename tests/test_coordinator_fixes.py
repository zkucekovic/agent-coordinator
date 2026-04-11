"""Tests for coordinator config loading, task sync, file hashing, and retry prompt."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_coordinator.application.task_service import TaskService
from agent_coordinator.cli import (
    _CoordinatorContext,
    _DEFAULT_AGENTS,
    _HANDOFF_TO_TASK_STATUS,
    _file_hash,
    _normalize_handoff_from_text,
    _record_turn_result,
    _retry_prompt,
    _sync_task_status,
    load_agent_config,
    load_config,
    load_retry_policy,
)
from agent_coordinator.domain.models import HandoffStatus, RunResult, TaskStatus, WorkflowState
from agent_coordinator.domain.retry_policy import RetryPolicy
from agent_coordinator.infrastructure.event_log import EventLog
from agent_coordinator.infrastructure.handoff_reader import HandoffReader
from agent_coordinator.infrastructure.session_store import SessionStore
from agent_coordinator.infrastructure.task_repository import JsonTaskRepository
from agent_coordinator.infrastructure.workflow_state_repository import WorkflowStateRepository


class TestLoadConfig(unittest.TestCase):
    """P1: Config is loaded once and shared."""

    def setUp(self):
        self._dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_load_config_returns_full_dict(self):
        cfg = {
            "retry_policy": {"max_rework": 5, "on_exceed": "blocked"},
            "agents": {"arch": {"model": "gpt-4", "prompt_file": "p.md"}},
        }
        (self._dir / "agents.json").write_text(json.dumps(cfg))
        result = load_config(self._dir)
        self.assertEqual(result, cfg)

    def test_load_config_missing_file_returns_empty(self):
        result = load_config(self._dir)
        self.assertEqual(result, {})

    def test_load_agent_config_from_loaded(self):
        cfg = {"agents": {"custom": {"model": None}}}
        agents = load_agent_config(cfg)
        self.assertIn("custom", agents)

    def test_load_agent_config_empty_returns_defaults(self):
        agents = load_agent_config({})
        self.assertEqual(agents, _DEFAULT_AGENTS)

    def test_load_retry_policy_from_loaded(self):
        cfg = {"retry_policy": {"max_rework": 7, "on_exceed": "blocked"}}
        policy = load_retry_policy(cfg)
        self.assertEqual(policy.max_rework, 7)
        self.assertEqual(policy.on_exceed, "blocked")

    def test_load_retry_policy_empty_returns_default(self):
        policy = load_retry_policy({})
        self.assertEqual(policy, RetryPolicy())


class TestSyncTaskStatus(unittest.TestCase):
    """P2: Automatic task status synchronization."""

    def setUp(self):
        self._dir = Path(tempfile.mkdtemp())
        self._tasks_path = self._dir / "tasks.json"

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def _make_service(self, tasks: list[dict]) -> TaskService:
        payload = {"version": 1, "tasks": tasks}
        self._tasks_path.write_text(json.dumps(payload))
        return TaskService(JsonTaskRepository(self._tasks_path))

    def test_sync_continue_transitions_to_in_engineering(self):
        svc = self._make_service([{"id": "t1", "title": "Test", "status": "ready_for_engineering"}])
        _sync_task_status(svc, "t1", HandoffStatus.CONTINUE, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.IN_ENGINEERING)

    def test_sync_review_required_transitions(self):
        svc = self._make_service([{"id": "t1", "title": "Test", "status": "in_engineering"}])
        _sync_task_status(svc, "t1", HandoffStatus.REVIEW_REQUIRED, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.READY_FOR_ARCHITECT_REVIEW)

    def test_sync_approved_transitions_to_done(self):
        svc = self._make_service([{"id": "t1", "title": "Test", "status": "ready_for_architect_review"}])
        _sync_task_status(svc, "t1", HandoffStatus.APPROVED, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.DONE)

    def test_sync_rework_required_transitions(self):
        svc = self._make_service([{"id": "t1", "title": "Test", "status": "ready_for_architect_review"}])
        _sync_task_status(svc, "t1", HandoffStatus.REWORK_REQUIRED, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.REWORK_REQUESTED)

    def test_sync_skips_when_no_task_service(self):
        # Should not raise
        _sync_task_status(None, "t1", HandoffStatus.APPROVED, verbose=False)

    def test_sync_skips_unknown_task(self):
        svc = self._make_service([{"id": "t1", "title": "Test", "status": "planned"}])
        # Should not raise for unknown task
        _sync_task_status(svc, "t-unknown", HandoffStatus.APPROVED, verbose=False)

    def test_sync_skips_invalid_transition(self):
        svc = self._make_service([{"id": "t1", "title": "Test", "status": "planned"}])
        # planned -> done is not valid, should skip silently
        _sync_task_status(svc, "t1", HandoffStatus.APPROVED, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.PLANNED)

    def test_sync_skips_plan_complete(self):
        svc = self._make_service([{"id": "t1", "title": "Test", "status": "done"}])
        # plan_complete has no mapping, should skip
        _sync_task_status(svc, "t1", HandoffStatus.PLAN_COMPLETE, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.DONE)

    def test_sync_skips_same_status(self):
        svc = self._make_service([{"id": "t1", "title": "Test", "status": "in_engineering"}])
        # Already in_engineering, CONTINUE maps to in_engineering — should skip
        _sync_task_status(svc, "t1", HandoffStatus.CONTINUE, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.IN_ENGINEERING)


class TestFileHash(unittest.TestCase):
    """P3: Content-based change detection."""

    def setUp(self):
        self._dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_hash_changes_when_content_changes(self):
        f = self._dir / "test.md"
        f.write_text("version 1")
        h1 = _file_hash(f)
        f.write_text("version 2")
        h2 = _file_hash(f)
        self.assertNotEqual(h1, h2)

    def test_hash_same_for_same_content(self):
        f = self._dir / "test.md"
        f.write_text("same content")
        h1 = _file_hash(f)
        h2 = _file_hash(f)
        self.assertEqual(h1, h2)

    def test_hash_missing_file_returns_empty(self):
        result = _file_hash(self._dir / "nonexistent.md")
        self.assertEqual(result, "")


class TestRetryPrompt(unittest.TestCase):
    """P4: Retry prompt is well-formed."""

    def test_contains_handoff_instruction(self):
        prompt = _retry_prompt("developer", Path("/workspace"))
        self.assertIn("---HANDOFF---", prompt)
        self.assertIn("---END---", prompt)
        self.assertIn("/workspace/handoff.md", prompt)

    def test_mentions_previous_failure(self):
        prompt = _retry_prompt("architect", Path("/ws"))
        self.assertIn("did NOT append", prompt)


class TestHandoffToTaskStatusMapping(unittest.TestCase):
    """P2: Verify the mapping table is complete for expected statuses."""

    def test_continue_maps_to_in_engineering(self):
        self.assertEqual(_HANDOFF_TO_TASK_STATUS[HandoffStatus.CONTINUE], TaskStatus.IN_ENGINEERING)

    def test_review_required_maps(self):
        self.assertEqual(_HANDOFF_TO_TASK_STATUS[HandoffStatus.REVIEW_REQUIRED], TaskStatus.READY_FOR_ARCHITECT_REVIEW)

    def test_rework_required_maps(self):
        self.assertEqual(_HANDOFF_TO_TASK_STATUS[HandoffStatus.REWORK_REQUIRED], TaskStatus.REWORK_REQUESTED)

    def test_approved_maps_to_done(self):
        self.assertEqual(_HANDOFF_TO_TASK_STATUS[HandoffStatus.APPROVED], TaskStatus.DONE)

    def test_blocked_maps(self):
        self.assertEqual(_HANDOFF_TO_TASK_STATUS[HandoffStatus.BLOCKED], TaskStatus.BLOCKED)

    def test_needs_human_maps(self):
        self.assertEqual(_HANDOFF_TO_TASK_STATUS[HandoffStatus.NEEDS_HUMAN], TaskStatus.NEEDS_HUMAN)

    def test_plan_complete_not_mapped(self):
        self.assertNotIn(HandoffStatus.PLAN_COMPLETE, _HANDOFF_TO_TASK_STATUS)


class TestDerivedLogging(unittest.TestCase):
    def test_duplicate_transition_is_not_appended_twice(self):
        temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        state_dir = temp_dir / ".agent-coordinator"
        state_dir.mkdir()
        handoff_path = temp_dir / "handoff.md"
        handoff_path.write_text(
            """---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: architect
TASK_ID: task-001
TITLE: Build auth
SUMMARY: start
ACCEPTANCE:
- done
CONSTRAINTS:
- none
FILES_TO_TOUCH:
- auth.py
CHANGED_FILES:
- none
VALIDATION:
- none
BLOCKERS:
- none
---END---
"""
        )
        tasks_path = temp_dir / "tasks.json"
        tasks_path.write_text(
            json.dumps({"tasks": [{"id": "task-001", "title": "Build auth", "status": "planned", "mode": "implementation"}]})
        )
        task_service = TaskService(JsonTaskRepository(tasks_path))
        workflow_repo = WorkflowStateRepository(state_dir / "workflow_state.json")
        workflow_state = WorkflowState(pending_task_id="task-001", pending_actor="developer", pending_status="planned")
        workflow_repo.save(workflow_state)
        prompt_file = state_dir / "prompts_log" / "turn-001-developer.md"
        prompt_file.parent.mkdir()
        prompt_file.write_text("prompt")

        ctx = _CoordinatorContext(
            workspace=temp_dir,
            state=state_dir,
            config={},
            agents={},
            default_backend="copilot",
            handoff_path=handoff_path,
            handoff_reader=HandoffReader(handoff_path),
            session_store=SessionStore(state_dir / "sessions.json"),
            event_log=EventLog(state_dir / "events.jsonl"),
            workflow_state_repo=workflow_repo,
            workflow_state=workflow_state,
            router=MagicMock(),
            builder=MagicMock(),
            runner_cache={},
            task_service=task_service,
            display=MagicMock(),
            interrupt_menu=MagicMock(),
            verbose=False,
            auto=True,
            stateless=False,
            logger=MagicMock(),
        )
        task = task_service.get("task-001")
        result = RunResult(
            session_id="s1",
            text="""---HANDOFF---
ROLE: developer
STATUS: review_required
NEXT: architect
TASK_ID: task-001
TITLE: Build auth
SUMMARY: implemented auth
ACCEPTANCE:
- auth works
CONSTRAINTS:
- none
FILES_TO_TOUCH:
- auth.py
CHANGED_FILES:
- auth.py
VALIDATION:
- python -m unittest
BLOCKERS:
- none
---END---
""",
        )

        with patch("agent_coordinator.cli.time.sleep"):
            _record_turn_result(ctx, "developer", task, "planned", 0.0, [], True, result, prompt_file, "hash")
            _record_turn_result(ctx, "developer", task, "planned", 0.0, [], True, result, prompt_file, "hash")

        handoff_content = handoff_path.read_text()
        self.assertEqual(handoff_content.count("implemented auth"), 1)
        self.assertEqual(len(ctx.event_log.read_all()), 1)


class TestNormalizeHandoffFromText(unittest.TestCase):
    """Tests for _normalize_handoff_from_text fallback normalizer."""

    def test_normalizes_loose_fields(self):
        text = (
            "Here is my update:\n\n"
            "ROLE: developer\n"
            "STATUS: done\n"
            "NEXT: qa_engineer\n"
            "TASK_ID: task-42\n"
            "TITLE: Implement login\n"
            "SUMMARY: Added JWT auth flow\n"
            "ACCEPTANCE:\n- tests pass\n"
            "CHANGED_FILES:\n- src/auth.py\n"
        )
        result = _normalize_handoff_from_text(text)
        self.assertIsNotNone(result)
        self.assertIn("---HANDOFF---", result)
        self.assertIn("---END---", result)
        self.assertIn("ROLE: developer", result)
        self.assertIn("TASK_ID: task-42", result)

    def test_returns_none_when_fields_missing(self):
        text = "ROLE: developer\nSTATUS: done\nSome random text"
        result = _normalize_handoff_from_text(text)
        self.assertIsNone(result)

    def test_all_six_required_fields_needed(self):
        text = (
            "ROLE: developer\n"
            "STATUS: done\n"
            "NEXT: qa_engineer\n"
            "TASK_ID: task-1\n"
            "TITLE: Fix bug\n"
            # Missing SUMMARY
        )
        result = _normalize_handoff_from_text(text)
        self.assertIsNone(result)

    def test_normalized_block_is_parseable(self):
        from agent_coordinator.handoff_parser import extract_latest

        text = (
            "ROLE: architect\n"
            "STATUS: continue\n"
            "NEXT: developer\n"
            "TASK_ID: task-99\n"
            "TITLE: Design API\n"
            "SUMMARY: Created API spec\n"
            "ACCEPTANCE:\n- spec reviewed\n"
            "CONSTRAINTS:\n- REST only\n"
            "FILES_TO_TOUCH:\n- api.py\n"
            "CHANGED_FILES:\n- docs/api.md\n"
            "VALIDATION:\n- linter passes\n"
            "BLOCKERS:\n- none\n"
        )
        result = _normalize_handoff_from_text(text)
        self.assertIsNotNone(result)
        message, errors = extract_latest(result)
        self.assertIsNotNone(message)
        self.assertEqual(message.role, "architect")
        self.assertEqual(message.task_id, "task-99")


if __name__ == "__main__":
    unittest.main()
