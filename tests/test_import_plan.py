"""Tests for import_plan.py — document parsing and workspace bootstrap."""

from __future__ import annotations

import json
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_coordinator.handoff_parser import extract_latest
from agent_coordinator.helpers.import_plan import (
    build_handoff_from_plan,
    build_handoff_from_spec,
    detect_doc_type,
    extract_tasks_from_plan,
    extract_title,
    import_document,
)

PLAN_PHASE_FORMAT = textwrap.dedent("""\
    # Implementation Plan — Auth Service

    ## Overview
    Build JWT authentication.

    ## Phases

    ### Phase 1 — Repository setup (task-001)
    Create the directory structure and placeholder files.

    ### Phase 2 — Domain Models (task-002)
    Define User and Token dataclasses.
    - Acceptance: User model importable from src.models
    - Acceptance: Token model has expiry field

    ### Phase 3 — API Endpoints (task-003)
    Implement POST /auth/login and POST /auth/logout.

    ## Constraints
    - Python 3.10+
    - No external dependencies
""")

PLAN_NUMBERED_FORMAT = textwrap.dedent("""\
    # Feature Plan

    ## Tasks

    ### 1. Setup project
    Initialize the repository.

    ### 2. Implement core logic
    Write the main module.

    ### 3. Write tests
    Cover all edge cases.
""")

PLAN_TASK_HEADING_FORMAT = textwrap.dedent("""\
    # Backend Refactor

    ### task-010: Extract repository layer
    Move database calls into a repository class.

    ### task-011 — Add caching layer
    Wrap repository calls with an in-memory cache.
""")

SPEC_CONTENT = textwrap.dedent("""\
    # User Authentication

    ## Overview
    JWT-based login, logout, and refresh.

    ## Requirements
    - POST /auth/login returns a signed JWT
    - POST /auth/logout invalidates the token
    - Tokens expire after 1 hour

    ## Constraints
    - Use existing User model
    - No new dependencies

    ## Acceptance Criteria
    - All endpoints return correct HTTP status codes
    - Tests cover happy path and error cases
""")


class TestDetectDocType(unittest.TestCase):
    def test_detects_plan(self):
        self.assertEqual(detect_doc_type(PLAN_PHASE_FORMAT), "plan")

    def test_detects_spec(self):
        self.assertEqual(detect_doc_type(SPEC_CONTENT), "spec")

    def test_numbered_plan(self):
        self.assertEqual(detect_doc_type(PLAN_NUMBERED_FORMAT), "plan")


class TestExtractTitle(unittest.TestCase):
    def test_extracts_h1(self):
        self.assertEqual(extract_title("# My Project\n\nSome text"), "My Project")

    def test_fallback_when_no_h1(self):
        self.assertEqual(extract_title("## Subheading only"), "Imported Document")

    def test_strips_whitespace(self):
        self.assertEqual(extract_title("#   Spaced Title  "), "Spaced Title")


class TestExtractTasksPhaseFormat(unittest.TestCase):
    def setUp(self):
        self.tasks = extract_tasks_from_plan(PLAN_PHASE_FORMAT)

    def test_extracts_three_tasks(self):
        self.assertEqual(len(self.tasks), 3)

    def test_task_ids(self):
        ids = [t["id"] for t in self.tasks]
        self.assertEqual(ids, ["task-001", "task-002", "task-003"])

    def test_task_titles(self):
        titles = [t["title"] for t in self.tasks]
        self.assertIn("Repository setup", titles[0])
        self.assertIn("Domain Models", titles[1])
        self.assertIn("API Endpoints", titles[2])

    def test_all_planned_status(self):
        for t in self.tasks:
            self.assertEqual(t["status"], "planned")

    def test_acceptance_criteria_extracted(self):
        # task-002 has two acceptance criteria
        t2 = next(t for t in self.tasks if t["id"] == "task-002")
        self.assertEqual(len(t2["acceptance_criteria"]), 2)

    def test_required_fields_present(self):
        for t in self.tasks:
            for field in (
                "id",
                "title",
                "status",
                "acceptance_criteria",
                "depends_on",
                "rework_count",
                "created_at",
                "updated_at",
            ):
                self.assertIn(field, t)


class TestExtractTasksNumberedFormat(unittest.TestCase):
    def setUp(self):
        self.tasks = extract_tasks_from_plan(PLAN_NUMBERED_FORMAT)

    def test_extracts_three_tasks(self):
        self.assertEqual(len(self.tasks), 3)

    def test_auto_assigned_ids(self):
        ids = [t["id"] for t in self.tasks]
        self.assertEqual(ids, ["task-001", "task-002", "task-003"])


class TestExtractTasksTaskHeadingFormat(unittest.TestCase):
    def setUp(self):
        self.tasks = extract_tasks_from_plan(PLAN_TASK_HEADING_FORMAT)

    def test_extracts_two_tasks(self):
        self.assertEqual(len(self.tasks), 2)

    def test_preserves_explicit_ids(self):
        ids = [t["id"] for t in self.tasks]
        self.assertIn("task-010", ids)
        self.assertIn("task-011", ids)


class TestExtractTasksEmpty(unittest.TestCase):
    def test_no_tasks_returns_empty_list(self):
        tasks = extract_tasks_from_plan("# Just a heading\n\nSome text with no tasks.")
        self.assertEqual(tasks, [])


class TestHandoffGeneration(unittest.TestCase):
    def test_spec_handoff_is_valid(self):
        handoff = build_handoff_from_spec("My Project")
        message, errors = extract_latest(handoff)
        self.assertIsNotNone(message, f"Handoff parse failed: {errors}")
        self.assertEqual(message.next, "architect")
        self.assertEqual(message.role, "human")

    def test_plan_handoff_is_valid(self):
        tasks = extract_tasks_from_plan(PLAN_PHASE_FORMAT)
        handoff = build_handoff_from_plan("My Plan", tasks)
        message, errors = extract_latest(handoff)
        self.assertIsNotNone(message, f"Handoff parse failed: {errors}")
        self.assertEqual(message.next, "architect")
        self.assertEqual(message.task_id, "task-001")

    def test_plan_handoff_empty_tasks(self):
        handoff = build_handoff_from_plan("Empty Plan", [])
        message, errors = extract_latest(handoff)
        self.assertIsNotNone(message, f"Handoff parse failed: {errors}")


class TestImportDocument(unittest.TestCase):
    def _import(self, source, workspace, **kwargs):
        """Convenience wrapper: always non-interactive in tests."""
        import_document(source, workspace, verbose=False, interactive=False, **kwargs)

    def test_import_spec_creates_files(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "SPECIFICATION.md"
            source.write_text(SPEC_CONTENT)

            self._import(source, workspace, doc_type="spec")

            self.assertTrue((workspace / "SPECIFICATION.md").exists())
            self.assertTrue((workspace / "handoff.md").exists())

    def test_import_spec_creates_bootstrap_tasks_json(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "SPECIFICATION.md"
            source.write_text(SPEC_CONTENT)

            self._import(source, workspace, doc_type="spec")

            data = json.loads((workspace / "tasks.json").read_text())
            self.assertEqual(data["tasks"][0]["id"], "task-000")
            self.assertEqual(data["tasks"][0]["mode"], "planning")

    def test_import_spec_content_intact(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "SPECIFICATION.md"
            source.write_text(SPEC_CONTENT)

            self._import(source, workspace, doc_type="spec")

            content = (workspace / "SPECIFICATION.md").read_text()
            self.assertEqual(content, SPEC_CONTENT)

    def test_import_plan_creates_tasks_json(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "plan.md"
            source.write_text(PLAN_PHASE_FORMAT)

            self._import(source, workspace, doc_type="plan")

            tasks_path = workspace / "tasks.json"
            self.assertTrue(tasks_path.exists())
            data = json.loads(tasks_path.read_text())
            self.assertEqual(len(data["tasks"]), 3)

    def test_import_plan_creates_handoff(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "plan.md"
            source.write_text(PLAN_PHASE_FORMAT)

            self._import(source, workspace, doc_type="plan")

            self.assertTrue((workspace / "handoff.md").exists())

    def test_import_plan_handoff_parseable(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "plan.md"
            source.write_text(PLAN_PHASE_FORMAT)

            self._import(source, workspace, doc_type="plan")

            content = (workspace / "handoff.md").read_text()
            message, errors = extract_latest(content)
            self.assertIsNotNone(message, f"Generated handoff invalid: {errors}")

    def test_no_overwrite_without_force(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            source = Path(tmp) / "plan.md"
            source.write_text(PLAN_PHASE_FORMAT)
            existing = workspace / "plan.md"
            existing.write_text("original content")

            self._import(source, workspace, doc_type="plan", force=False)

            self.assertEqual(existing.read_text(), "original content")

    def test_force_overwrites(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            source = Path(tmp) / "plan.md"
            source.write_text(PLAN_PHASE_FORMAT)
            existing = workspace / "plan.md"
            existing.write_text("original content")

            self._import(source, workspace, doc_type="plan", force=True)

            self.assertNotEqual(existing.read_text(), "original content")

    def test_no_tasks_flag(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "plan.md"
            source.write_text(PLAN_PHASE_FORMAT)

            self._import(source, workspace, doc_type="plan", no_tasks=True)

            self.assertFalse((workspace / "tasks.json").exists())

    def test_no_handoff_flag(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "SPEC.md"
            source.write_text(SPEC_CONTENT)

            self._import(source, workspace, doc_type="spec", no_handoff=True)

            self.assertFalse((workspace / "handoff.md").exists())

    def test_autodetect_spec(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "input.md"
            source.write_text(SPEC_CONTENT)

            self._import(source, workspace, doc_type=None)

            self.assertTrue((workspace / "SPECIFICATION.md").exists())

    def test_autodetect_plan(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "input.md"
            source.write_text(PLAN_PHASE_FORMAT)

            self._import(source, workspace, doc_type=None)

            self.assertTrue((workspace / "plan.md").exists())


if __name__ == "__main__":
    unittest.main()
