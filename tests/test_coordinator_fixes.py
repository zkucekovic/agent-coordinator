"""Tests for coordinator config loading, task sync, file hashing, and retry prompt."""

import json
import tempfile
import shutil
import unittest
from pathlib import Path

from coordinator import (
    load_config,
    load_agent_config,
    load_retry_policy,
    _sync_task_status,
    _file_hash,
    _retry_prompt,
    _DEFAULT_AGENTS,
    _HANDOFF_TO_TASK_STATUS,
)
from src.application.task_service import TaskService
from src.domain.models import HandoffStatus, Task, TaskStatus
from src.domain.retry_policy import RetryPolicy
from src.infrastructure.task_repository import JsonTaskRepository


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
        svc = self._make_service([
            {"id": "t1", "title": "Test", "status": "ready_for_engineering"}
        ])
        _sync_task_status(svc, "t1", HandoffStatus.CONTINUE, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.IN_ENGINEERING)

    def test_sync_review_required_transitions(self):
        svc = self._make_service([
            {"id": "t1", "title": "Test", "status": "in_engineering"}
        ])
        _sync_task_status(svc, "t1", HandoffStatus.REVIEW_REQUIRED, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.READY_FOR_ARCHITECT_REVIEW)

    def test_sync_approved_transitions_to_done(self):
        svc = self._make_service([
            {"id": "t1", "title": "Test", "status": "ready_for_architect_review"}
        ])
        _sync_task_status(svc, "t1", HandoffStatus.APPROVED, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.DONE)

    def test_sync_rework_required_transitions(self):
        svc = self._make_service([
            {"id": "t1", "title": "Test", "status": "ready_for_architect_review"}
        ])
        _sync_task_status(svc, "t1", HandoffStatus.REWORK_REQUIRED, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.REWORK_REQUESTED)

    def test_sync_skips_when_no_task_service(self):
        # Should not raise
        _sync_task_status(None, "t1", HandoffStatus.APPROVED, verbose=False)

    def test_sync_skips_unknown_task(self):
        svc = self._make_service([
            {"id": "t1", "title": "Test", "status": "planned"}
        ])
        # Should not raise for unknown task
        _sync_task_status(svc, "t-unknown", HandoffStatus.APPROVED, verbose=False)

    def test_sync_skips_invalid_transition(self):
        svc = self._make_service([
            {"id": "t1", "title": "Test", "status": "planned"}
        ])
        # planned -> done is not valid, should skip silently
        _sync_task_status(svc, "t1", HandoffStatus.APPROVED, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.PLANNED)

    def test_sync_skips_plan_complete(self):
        svc = self._make_service([
            {"id": "t1", "title": "Test", "status": "done"}
        ])
        # plan_complete has no mapping, should skip
        _sync_task_status(svc, "t1", HandoffStatus.PLAN_COMPLETE, verbose=False)
        self.assertEqual(svc.get("t1").status, TaskStatus.DONE)

    def test_sync_skips_same_status(self):
        svc = self._make_service([
            {"id": "t1", "title": "Test", "status": "in_engineering"}
        ])
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


if __name__ == "__main__":
    unittest.main()
