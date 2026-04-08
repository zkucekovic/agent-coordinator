"""Tests for src.application.task_service (TaskService + next_ready_task + retry)."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent_coordinator.application.task_service import TaskService
from agent_coordinator.domain.models import TaskStatus
from agent_coordinator.domain.retry_policy import RetryPolicy
from agent_coordinator.infrastructure.task_repository import JsonTaskRepository


def _make_service(tasks: list[dict], retry_policy: RetryPolicy | None = None) -> tuple[TaskService, Path]:
    """Create a TaskService backed by a temp tasks.json file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir=tempfile.gettempdir()) as tmp:
        json.dump({"tasks": tasks}, tmp)
        tmp.flush()
    path = Path(tmp.name)
    repo = JsonTaskRepository(path)
    service = TaskService(repo, retry_policy=retry_policy)
    return service, path


class TestNextReadyTask(unittest.TestCase):
    def tearDown(self):
        # cleanup handled per-test via path
        pass

    def test_returns_first_planned_task_with_no_deps(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "planned"},
                {"id": "t2", "title": "B", "status": "planned"},
            ]
        )
        task = svc.next_ready_task()
        os.unlink(path)
        self.assertIsNotNone(task)
        self.assertEqual(task.id, "t1")

    def test_skips_task_with_unmet_dependency(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "planned", "depends_on": ["t2"]},
                {"id": "t2", "title": "B", "status": "planned"},
            ]
        )
        task = svc.next_ready_task()
        os.unlink(path)
        # t1 depends on t2 which isn't done — should return t2
        self.assertEqual(task.id, "t2")

    def test_returns_task_once_dependency_done(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "planned", "depends_on": ["t2"]},
                {"id": "t2", "title": "B", "status": "done"},
            ]
        )
        task = svc.next_ready_task()
        os.unlink(path)
        self.assertEqual(task.id, "t1")

    def test_returns_none_when_all_done(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "done"},
            ]
        )
        task = svc.next_ready_task()
        os.unlink(path)
        self.assertIsNone(task)

    def test_returns_rework_requested_task(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "rework_requested"},
            ]
        )
        task = svc.next_ready_task()
        os.unlink(path)
        self.assertEqual(task.id, "t1")


class TestIncrementRework(unittest.TestCase):
    def test_within_limit_returns_rework_requested(self):
        svc, path = _make_service(
            [{"id": "t1", "title": "A", "status": "ready_for_architect_review"}],
            retry_policy=RetryPolicy(max_rework=3),
        )
        new_status = svc.increment_rework("t1")
        os.unlink(path)
        self.assertEqual(new_status, TaskStatus.REWORK_REQUESTED)

    def test_at_limit_returns_on_exceed_status(self):
        svc, path = _make_service(
            [{"id": "t1", "title": "A", "status": "ready_for_architect_review", "rework_count": 2}],
            retry_policy=RetryPolicy(max_rework=3, on_exceed="needs_human"),
        )
        new_status = svc.increment_rework("t1")
        task = svc.get("t1")
        os.unlink(path)
        self.assertEqual(new_status, TaskStatus.NEEDS_HUMAN)
        self.assertEqual(task.status, TaskStatus.NEEDS_HUMAN)

    def test_unlimited_policy_never_escalates(self):
        svc, path = _make_service(
            [{"id": "t1", "title": "A", "status": "ready_for_architect_review", "rework_count": 99}],
            retry_policy=RetryPolicy.unlimited(),
        )
        new_status = svc.increment_rework("t1")
        os.unlink(path)
        self.assertEqual(new_status, TaskStatus.REWORK_REQUESTED)

    def test_rework_count_persists(self):
        svc, path = _make_service(
            [{"id": "t1", "title": "A", "status": "ready_for_architect_review"}],
            retry_policy=RetryPolicy(max_rework=5),
        )
        svc.increment_rework("t1")
        # Reload from disk
        repo2 = JsonTaskRepository(path)
        svc2 = TaskService(repo2)
        task = svc2.get("t1")
        os.unlink(path)
        self.assertEqual(task.rework_count, 1)

    def test_unknown_task_raises(self):
        svc, path = _make_service([])
        with self.assertRaises(ValueError):
            svc.increment_rework("nope")
        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
