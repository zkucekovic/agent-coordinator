"""Tests for workflow state persistence and loop recovery helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from agent_coordinator.application.task_service import TaskService
from agent_coordinator.cli import _recover_from_coordination_loop
from agent_coordinator.domain.models import WorkflowState
from agent_coordinator.infrastructure.task_repository import JsonTaskRepository
from agent_coordinator.infrastructure.workflow_state_repository import WorkflowStateRepository


class TestWorkflowStateRepository(unittest.TestCase):
    def test_round_trips_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflow_state.json"
            repo = WorkflowStateRepository(path)
            state = WorkflowState(
                pending_task_id="task-001",
                pending_actor="developer",
                pending_status="planned",
                pending_summary="do the work",
                transition_keys=["k1"],
                no_progress_turns=1,
                recovery_count=2,
            )
            repo.save(state)
            loaded = repo.load()
            self.assertEqual(loaded.pending_task_id, "task-001")
            self.assertEqual(loaded.pending_actor, "developer")
            self.assertEqual(loaded.transition_keys, ["k1"])
            self.assertEqual(loaded.recovery_count, 2)


class TestLoopRecovery(unittest.TestCase):
    def test_recovery_prefers_executable_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks_path = Path(tmp) / "tasks.json"
            tasks_path.write_text(
                json.dumps(
                    {
                        "tasks": [
                            {"id": "task-000", "title": "Create plan", "status": "planned", "mode": "planning"},
                            {
                                "id": "task-001",
                                "title": "Add middleware",
                                "status": "planned",
                                "mode": "implementation",
                                "acceptance_criteria": ["middleware exists"],
                            },
                        ]
                    }
                )
            )
            service = TaskService(JsonTaskRepository(tasks_path))
            repo = WorkflowStateRepository(Path(tmp) / "workflow_state.json")
            state = WorkflowState(
                pending_task_id="task-000",
                pending_actor="architect",
                pending_status="ready_for_engineering",
                no_progress_turns=2,
            )
            ctx = SimpleNamespace(task_service=service, workflow_state=state, workflow_state_repo=repo)
            _recover_from_coordination_loop(ctx)
            self.assertEqual(state.pending_task_id, "task-001")
            self.assertEqual(state.pending_actor, "developer")
            self.assertEqual(state.no_progress_turns, 0)
