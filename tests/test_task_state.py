"""Tests for task state and lifecycle rules."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from src.task_store import TaskStore
from src.models import TaskStatus

SAMPLE_TASKS = {
    "tasks": [
        {
            "id": "task-A",
            "title": "Task Alpha",
            "status": "planned",
            "acceptance_criteria": ["Do thing A", "Do thing B"]
        },
        {
            "id": "task-B",
            "title": "Task Beta",
            "status": "planned",
            "acceptance_criteria": []
        }
    ]
}


class TestTaskStore(unittest.TestCase):

    def setUp(self):
        self._tf = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False,
            dir=os.path.dirname(os.path.abspath(__file__))
        )
        json.dump(SAMPLE_TASKS, self._tf)
        self._tf.flush()
        self._tf.close()
        self.store = TaskStore(self._tf.name)

    def tearDown(self):
        os.unlink(self._tf.name)

    def test_loads_from_json(self):
        tasks = self.store.all()
        self.assertEqual(len(tasks), 2)

    def test_get_returns_correct_task(self):
        task = self.store.get("task-A")
        self.assertIsNotNone(task)
        self.assertEqual(task.title, "Task Alpha")
        self.assertEqual(task.status, TaskStatus.PLANNED)

    def test_get_nonexistent_returns_none(self):
        result = self.store.get("no-such-id")
        self.assertIsNone(result)

    def test_all_returns_all_tasks(self):
        all_tasks = self.store.all()
        ids = {t.id for t in all_tasks}
        self.assertIn("task-A", ids)
        self.assertIn("task-B", ids)

    def test_update_status_valid_transition(self):
        self.store.update_status("task-A", TaskStatus.IN_ENGINEERING)
        task = self.store.get("task-A")
        self.assertEqual(task.status, TaskStatus.IN_ENGINEERING)

    def test_update_status_persists(self):
        self.store.update_status("task-A", TaskStatus.IN_ENGINEERING)
        fresh = TaskStore(self._tf.name)
        self.assertEqual(fresh.get("task-A").status, TaskStatus.IN_ENGINEERING)

    def test_update_status_invalid_transition_raises(self):
        # planned -> done is not a valid transition
        with self.assertRaises(ValueError):
            self.store.update_status("task-A", TaskStatus.DONE)

    def test_update_status_unknown_task_raises(self):
        with self.assertRaises(ValueError):
            self.store.update_status("ghost-task", TaskStatus.IN_ENGINEERING)

    def test_concurrency_guard_second_in_engineering_raises(self):
        self.store.update_status("task-A", TaskStatus.IN_ENGINEERING)
        with self.assertRaises(ValueError):
            self.store.update_status("task-B", TaskStatus.IN_ENGINEERING)

    def test_active_engineering_task_returns_correct(self):
        self.assertIsNone(self.store.active_engineering_task())
        self.store.update_status("task-A", TaskStatus.IN_ENGINEERING)
        active = self.store.active_engineering_task()
        self.assertIsNotNone(active)
        self.assertEqual(active.id, "task-A")

    def test_active_engineering_task_returns_none_when_empty(self):
        self.assertIsNone(self.store.active_engineering_task())

    def test_set_acceptance_criteria_persists(self):
        criteria = ["Criterion 1", "Criterion 2"]
        self.store.set_acceptance_criteria("task-A", criteria)
        fresh = TaskStore(self._tf.name)
        self.assertEqual(fresh.get("task-A").acceptance_criteria, criteria)

    def test_set_acceptance_criteria_unknown_task_raises(self):
        with self.assertRaises(ValueError):
            self.store.set_acceptance_criteria("ghost-task", ["x"])


if __name__ == '__main__':
    unittest.main()
