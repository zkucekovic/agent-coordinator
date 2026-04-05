"""Tests for src.infrastructure.task_repository (JsonTaskRepository)."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent_coordinator.domain.models import Task, TaskStatus
from agent_coordinator.infrastructure.task_repository import JsonTaskRepository


def _write_json(data: dict | list) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=tempfile.gettempdir()
    )
    json.dump(data, tmp)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


class TestJsonTaskRepositoryLoad(unittest.TestCase):

    def test_loads_versioned_format(self):
        path = _write_json({
            "version": 1,
            "tasks": [{"id": "t1", "title": "A", "status": "planned"}],
        })
        repo = JsonTaskRepository(path)
        os.unlink(path)
        self.assertIsNotNone(repo.get("t1"))

    def test_normalises_bare_list_format(self):
        path = _write_json([{"id": "t1", "title": "A", "status": "planned"}])
        repo = JsonTaskRepository(path)
        os.unlink(path)
        self.assertIsNotNone(repo.get("t1"))

    def test_normalises_tasks_dict_format(self):
        path = _write_json({"tasks": [{"id": "t1", "title": "A", "status": "planned"}]})
        repo = JsonTaskRepository(path)
        os.unlink(path)
        self.assertIsNotNone(repo.get("t1"))

    def test_loads_rework_count_and_depends_on(self):
        path = _write_json({"tasks": [{
            "id": "t1", "title": "A", "status": "planned",
            "rework_count": 2, "depends_on": ["t0"],
        }]})
        repo = JsonTaskRepository(path)
        task = repo.get("t1")
        os.unlink(path)
        self.assertEqual(task.rework_count, 2)
        self.assertEqual(task.depends_on, ["t0"])

    def test_defaults_rework_count_to_zero(self):
        path = _write_json({"tasks": [{"id": "t1", "title": "A", "status": "planned"}]})
        repo = JsonTaskRepository(path)
        task = repo.get("t1")
        os.unlink(path)
        self.assertEqual(task.rework_count, 0)


class TestJsonTaskRepositorySave(unittest.TestCase):

    def test_save_writes_versioned_format(self):
        path = _write_json({"tasks": [{"id": "t1", "title": "A", "status": "planned"}]})
        repo = JsonTaskRepository(path)
        task = repo.get("t1")
        task.status = TaskStatus.DONE
        repo.save(task)
        raw = json.loads(path.read_text())
        os.unlink(path)
        self.assertEqual(raw["version"], 1)
        self.assertIn("tasks", raw)

    def test_save_persists_all_fields(self):
        path = _write_json({"tasks": [{
            "id": "t1", "title": "A", "status": "planned",
        }]})
        repo = JsonTaskRepository(path)
        task = repo.get("t1")
        task.rework_count = 3
        task.depends_on = ["t0"]
        task.acceptance_criteria = ["must pass"]
        repo.save(task)
        raw = json.loads(path.read_text())
        saved = raw["tasks"][0]
        os.unlink(path)
        self.assertEqual(saved["rework_count"], 3)
        self.assertEqual(saved["depends_on"], ["t0"])
        self.assertEqual(saved["acceptance_criteria"], ["must pass"])

    def test_get_unknown_returns_none(self):
        path = _write_json({"tasks": []})
        repo = JsonTaskRepository(path)
        os.unlink(path)
        self.assertIsNone(repo.get("nope"))

    def test_all_returns_all_tasks(self):
        path = _write_json({"tasks": [
            {"id": "t1", "title": "A", "status": "planned"},
            {"id": "t2", "title": "B", "status": "done"},
        ]})
        repo = JsonTaskRepository(path)
        os.unlink(path)
        self.assertEqual(len(repo.all()), 2)


if __name__ == "__main__":
    unittest.main()
