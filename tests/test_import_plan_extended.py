"""Extended tests for agent_coordinator/helpers/import_plan.py.

Targets uncovered branches:
- detect_doc_type returning "unknown"
- numbered-phase heading extraction (lines 122-123)
- duplicate task-ID deduplication (lines 133-134)
- _first_paragraph returning "" (line 179)
- _extract_bullets with no section_hint (line 195)
- _extract_bullets with numbered list items (line 203)
- import_document with unknown doc type falling back to "spec" (non-interactive path)
- import_document with force=True overwrites existing files
- import_document with no_handoff=True skips handoff.md
"""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_coordinator.helpers.import_plan import (
    _extract_bullets,
    _first_paragraph,
    detect_doc_type,
    extract_tasks_from_plan,
    import_document,
)

SPEC_CONTENT = textwrap.dedent("""\
    # User Authentication

    ## Overview
    JWT-based login, logout, and refresh.

    ## Requirements
    - POST /auth/login returns a signed JWT

    ## Constraints
    - Use existing User model

    ## Acceptance Criteria
    - All endpoints return correct HTTP status codes
""")

PLAN_PHASE_FORMAT = textwrap.dedent("""\
    # Implementation Plan

    ### Phase 1 — Setup (task-001)
    Create the directory structure.

    ### Phase 2 — Models (task-002)
    Define dataclasses.

    ### Phase 3 — API (task-003)
    Implement endpoints.
""")

UNKNOWN_CONTENT = textwrap.dedent("""\
    # Some Document

    This document has no plan or spec keywords.
    Just some plain prose without structure.
""")


class TestDetectDocTypeUnknown(unittest.TestCase):
    def test_plain_prose_returns_unknown(self):
        # No spec or plan keywords → "unknown"
        result = detect_doc_type(UNKNOWN_CONTENT)
        self.assertEqual(result, "unknown")

    def test_spec_content_returns_spec(self):
        self.assertEqual(detect_doc_type(SPEC_CONTENT), "spec")

    def test_plan_content_returns_plan(self):
        self.assertEqual(detect_doc_type(PLAN_PHASE_FORMAT), "plan")


class TestExtractTasksNumberedPhaseHeadings(unittest.TestCase):
    """Test the numbered-phase regex path (lines 122-123 in import_plan.py)."""

    PHASE_PLAN = textwrap.dedent("""\
        # Refactor Plan

        ### Phase 1 — Authentication
        Implement JWT auth.

        ### Phase 2 — Authorization
        Role-based access.

        ### Phase 3 — Logging
        Audit trail.
    """)

    STEP_PLAN = textwrap.dedent("""\
        # Migration Steps

        ## Step 1: Backup database
        Take a full snapshot.

        ## Step 2: Run migrations
        Apply schema changes.
    """)

    def test_phase_headings_extract_ids(self):
        tasks = extract_tasks_from_plan(self.PHASE_PLAN)
        ids = [t["id"] for t in tasks]
        self.assertIn("task-001", ids)
        self.assertIn("task-002", ids)
        self.assertIn("task-003", ids)

    def test_step_headings_extract_ids(self):
        tasks = extract_tasks_from_plan(self.STEP_PLAN)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["id"], "task-001")
        self.assertEqual(tasks[1]["id"], "task-002")

    def test_titles_captured(self):
        tasks = extract_tasks_from_plan(self.PHASE_PLAN)
        titles = [t["title"] for t in tasks]
        self.assertIn("Authentication", titles[0])
        self.assertIn("Authorization", titles[1])


class TestExtractTasksDuplicateIds(unittest.TestCase):
    """Test deduplication when the same task-ID appears more than once (lines 133-134)."""

    DUP_PLAN = textwrap.dedent("""\
        # Plan

        ### task-001: Initial setup
        Create files.

        ### task-001: Extended setup
        Additional setup work.
    """)

    def test_duplicate_ids_are_deduplicated(self):
        tasks = extract_tasks_from_plan(self.DUP_PLAN)
        ids = [t["id"] for t in tasks]
        # Both should appear but be distinct
        self.assertEqual(len(set(ids)), len(ids), f"Expected unique IDs but got: {ids}")

    def test_duplicate_ids_has_two_tasks(self):
        tasks = extract_tasks_from_plan(self.DUP_PLAN)
        self.assertEqual(len(tasks), 2)

    def test_first_task_retains_original_id(self):
        tasks = extract_tasks_from_plan(self.DUP_PLAN)
        self.assertEqual(tasks[0]["id"], "task-001")


class TestFirstParagraph(unittest.TestCase):
    """Test _first_paragraph returning empty string (line 179)."""

    def test_empty_input_returns_empty(self):
        self.assertEqual(_first_paragraph(""), "")

    def test_only_headings_returns_empty(self):
        text = "## Heading\n### Sub-heading\n#### Another"
        self.assertEqual(_first_paragraph(text), "")

    def test_only_bullet_list_returns_empty(self):
        text = "- item one\n- item two\n- item three"
        self.assertEqual(_first_paragraph(text), "")

    def test_normal_paragraph_returned(self):
        text = "## Heading\n\nThis is a paragraph."
        self.assertEqual(_first_paragraph(text), "This is a paragraph.")

    def test_first_non_heading_paragraph_returned(self):
        text = "## Section\n\nFirst real paragraph here.\n\nSecond paragraph."
        self.assertIn("First real paragraph", _first_paragraph(text))


class TestExtractBulletsNoSectionHint(unittest.TestCase):
    """Test _extract_bullets with no section_hint (line 195 — scope = text)."""

    def test_dash_bullets_extracted(self):
        text = "- item one\n- item two\n- item three"
        result = _extract_bullets(text)
        self.assertEqual(result, ["item one", "item two", "item three"])

    def test_asterisk_bullets_extracted(self):
        text = "* foo\n* bar"
        result = _extract_bullets(text)
        self.assertEqual(result, ["foo", "bar"])

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(_extract_bullets(""), [])

    def test_no_bullets_returns_empty_list(self):
        self.assertEqual(_extract_bullets("just plain prose here"), [])


class TestExtractBulletsNumberedList(unittest.TestCase):
    """Test _extract_bullets with numbered list items (line 203)."""

    def test_numbered_items_extracted(self):
        text = "1. First step\n2. Second step\n3. Third step"
        result = _extract_bullets(text)
        self.assertEqual(result, ["First step", "Second step", "Third step"])

    def test_mixed_numbered_and_dash_bullets(self):
        text = "- dash item\n1. numbered item"
        result = _extract_bullets(text)
        self.assertIn("dash item", result)
        self.assertIn("numbered item", result)

    def test_numbered_with_section_hint(self):
        text = "## Acceptance\n1. Passes tests\n2. No regressions\n"
        result = _extract_bullets(text, section_hint="acceptance")
        self.assertIn("Passes tests", result)
        self.assertIn("No regressions", result)


class TestImportDocumentUnknownType(unittest.TestCase):
    """Test the unknown doc-type path in import_document (non-interactive → 'spec')."""

    def test_unknown_type_non_interactive_defaults_to_spec(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "input.md"
            # No plan or spec keywords → detect_doc_type → "unknown"
            source.write_text(UNKNOWN_CONTENT)
            import_document(
                source_path=source,
                workspace=workspace,
                doc_type=None,
                force=False,
                no_handoff=False,
                verbose=False,
                interactive=False,
            )
            # Should have been treated as "spec"
            self.assertTrue((workspace / "SPECIFICATION.md").exists())

    def test_unknown_type_no_handoff_flag_respected(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "input.md"
            source.write_text(UNKNOWN_CONTENT)
            import_document(
                source_path=source,
                workspace=workspace,
                doc_type=None,
                force=False,
                no_handoff=True,
                verbose=False,
                interactive=False,
            )
            self.assertFalse((workspace / "handoff.md").exists())


class TestImportDocumentForce(unittest.TestCase):
    """Test force=True overwrites existing files."""

    def _do_import(self, source, workspace, **kwargs):
        import_document(source, workspace, verbose=False, interactive=False, **kwargs)

    def test_force_overwrites_spec(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            source = Path(tmp) / "SPECIFICATION.md"
            source.write_text(SPEC_CONTENT)
            existing = workspace / "SPECIFICATION.md"
            existing.write_text("old content")

            self._do_import(source, workspace, doc_type="spec", force=True)

            self.assertEqual((workspace / "SPECIFICATION.md").read_text(), SPEC_CONTENT)

    def test_no_force_preserves_existing_spec(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            source = Path(tmp) / "SPECIFICATION.md"
            source.write_text(SPEC_CONTENT)
            existing = workspace / "SPECIFICATION.md"
            existing.write_text("old content")

            self._do_import(source, workspace, doc_type="spec", force=False)

            self.assertEqual(existing.read_text(), "old content")

    def test_force_overwrites_handoff(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            source = Path(tmp) / "SPECIFICATION.md"
            source.write_text(SPEC_CONTENT)
            handoff = workspace / "handoff.md"
            handoff.write_text("old handoff")

            self._do_import(source, workspace, doc_type="spec", force=True)

            self.assertNotEqual(handoff.read_text(), "old handoff")

    def test_no_force_preserves_existing_handoff(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            source = Path(tmp) / "SPECIFICATION.md"
            source.write_text(SPEC_CONTENT)
            handoff = workspace / "handoff.md"
            handoff.write_text("original handoff content")

            self._do_import(source, workspace, doc_type="spec", force=False)

            self.assertEqual(handoff.read_text(), "original handoff content")


class TestImportDocumentNoHandoff(unittest.TestCase):
    """Test no_handoff=True skips handoff.md creation."""

    def _do_import(self, source, workspace, **kwargs):
        import_document(source, workspace, verbose=False, interactive=False, **kwargs)

    def test_no_handoff_spec(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "spec.md"
            source.write_text(SPEC_CONTENT)
            self._do_import(source, workspace, doc_type="spec", no_handoff=True)
            self.assertFalse((workspace / "handoff.md").exists())

    def test_no_handoff_plan(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "plan.md"
            source.write_text(PLAN_PHASE_FORMAT)
            self._do_import(source, workspace, doc_type="plan", no_handoff=True)
            self.assertFalse((workspace / "handoff.md").exists())

    def test_with_handoff_spec_creates_handoff(self):
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            source = Path(tmp) / "spec.md"
            source.write_text(SPEC_CONTENT)
            self._do_import(source, workspace, doc_type="spec", no_handoff=False)
            self.assertTrue((workspace / "handoff.md").exists())


if __name__ == "__main__":
    unittest.main()
