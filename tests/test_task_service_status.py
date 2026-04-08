"""Tests for src.application.task_service — update_status and acceptance criteria."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent_coordinator.application.task_service import TaskService
from agent_coordinator.domain.models import TaskStatus
from agent_coordinator.infrastructure.task_repository import JsonTaskRepository


def _make_service(tasks: list[dict]) -> tuple[TaskService, Path]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir=tempfile.gettempdir()) as tmp:
        json.dump({"tasks": tasks}, tmp)
        tmp.flush()
    path = Path(tmp.name)
    return TaskService(JsonTaskRepository(path)), path


class TestUpdateStatus(unittest.TestCase):
    def test_valid_transition_succeeds(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "planned"},
            ]
        )
        svc.update_status("t1", TaskStatus.READY_FOR_ENGINEERING)
        task = svc.get("t1")
        os.unlink(path)
        self.assertEqual(task.status, TaskStatus.READY_FOR_ENGINEERING)

    def test_invalid_transition_raises(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "planned"},
            ]
        )
        with self.assertRaises(ValueError):
            svc.update_status("t1", TaskStatus.DONE)
        os.unlink(path)

    def test_unknown_task_raises(self):
        svc, path = _make_service([])
        with self.assertRaises(ValueError):
            svc.update_status("ghost", TaskStatus.DONE)
        os.unlink(path)

    def test_concurrency_guard_blocks_second_in_engineering(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "in_engineering"},
                {"id": "t2", "title": "B", "status": "planned"},
            ]
        )
        with self.assertRaises(ValueError):
            svc.update_status("t2", TaskStatus.IN_ENGINEERING)
        os.unlink(path)

    def test_same_task_retransition_to_in_engineering_allowed(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "rework_requested"},
            ]
        )
        svc.update_status("t1", TaskStatus.IN_ENGINEERING)
        task = svc.get("t1")
        os.unlink(path)
        self.assertEqual(task.status, TaskStatus.IN_ENGINEERING)

    def test_status_persists_to_disk(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "planned"},
            ]
        )
        svc.update_status("t1", TaskStatus.READY_FOR_ENGINEERING)
        # Reload from disk
        svc2 = TaskService(JsonTaskRepository(path))
        task = svc2.get("t1")
        os.unlink(path)
        self.assertEqual(task.status, TaskStatus.READY_FOR_ENGINEERING)


class TestSetAcceptanceCriteria(unittest.TestCase):
    def test_sets_and_persists_criteria(self):
        svc, path = _make_service(
            [
                {"id": "t1", "title": "A", "status": "planned"},
            ]
        )
        svc.set_acceptance_criteria("t1", ["criterion 1", "criterion 2"])
        svc2 = TaskService(JsonTaskRepository(path))
        task = svc2.get("t1")
        os.unlink(path)
        self.assertEqual(task.acceptance_criteria, ["criterion 1", "criterion 2"])

    def test_unknown_task_raises(self):
        svc, path = _make_service([])
        with self.assertRaises(ValueError):
            svc.set_acceptance_criteria("ghost", ["x"])
        os.unlink(path)


if __name__ == "__main__":
    unittest.main()
