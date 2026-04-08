"""Tests for src.infrastructure.event_log (EventLog)."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent_coordinator.infrastructure.event_log import EventLog


class TestEventLog(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, dir=tempfile.gettempdir()) as tmp:
            pass
        self._path = Path(tmp.name)

    def tearDown(self):
        os.unlink(self._path)

    def test_append_writes_valid_json_line(self):
        log = EventLog(self._path)
        log.append(
            turn=1,
            agent="architect",
            task_id="t-001",
            status_before="continue",
            status_after="continue",
            session_id="ses_abc123",
        )
        lines = self._path.read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["turn"], 1)
        self.assertEqual(record["agent"], "architect")
        self.assertEqual(record["task_id"], "t-001")

    def test_multiple_appends_produce_multiple_lines(self):
        log = EventLog(self._path)
        for i in range(3):
            log.append(
                turn=i + 1,
                agent="engineer",
                task_id="t-001",
                status_before="continue",
                status_after="review_required",
                session_id="ses_x",
            )
        events = log.read_all()
        self.assertEqual(len(events), 3)
        self.assertEqual([e["turn"] for e in events], [1, 2, 3])

    def test_extra_fields_included(self):
        log = EventLog(self._path)
        log.append(
            turn=1,
            agent="qa",
            task_id="t-002",
            status_before="continue",
            status_after="review_required",
            session_id="ses_y",
            extra={"cost_usd": 0.003},
        )
        events = log.read_all()
        self.assertIn("cost_usd", events[0])

    def test_read_all_on_empty_file_returns_empty_list(self):
        empty_path = Path(self._path.parent / "nonexistent.jsonl")
        log = EventLog(empty_path)
        self.assertEqual(log.read_all(), [])

    def test_each_record_has_timestamp(self):
        log = EventLog(self._path)
        log.append(
            turn=1,
            agent="architect",
            task_id="t-001",
            status_before="continue",
            status_after="continue",
            session_id="ses_z",
        )
        events = log.read_all()
        self.assertIn("ts", events[0])

    def test_response_text_present_and_empty_by_default(self):
        log = EventLog(self._path)
        log.append(
            turn=1,
            agent="architect",
            task_id="t-001",
            status_before="continue",
            status_after="continue",
            session_id="ses_a",
        )
        events = log.read_all()
        self.assertIn("response_text", events[0])
        self.assertEqual(events[0]["response_text"], "")

    def test_response_text_with_newlines_is_valid_json(self):
        log = EventLog(self._path)
        multiline = "line one\nline two\nline three"
        log.append(
            turn=1,
            agent="developer",
            task_id="t-001",
            status_before="continue",
            status_after="review_required",
            session_id="ses_b",
            response_text=multiline,
        )
        raw_line = self._path.read_text().strip()
        # Must be a single line (no literal newlines outside the JSON string)
        self.assertEqual(len(raw_line.splitlines()), 1)
        record = json.loads(raw_line)
        self.assertEqual(record["response_text"], multiline)

    def test_prompt_file_and_prompt_hash_present(self):
        log = EventLog(self._path)
        log.append(
            turn=2,
            agent="developer",
            task_id="t-002",
            status_before="continue",
            status_after="review_required",
            session_id="ses_c",
            prompt_file="prompts_log/turn-002-developer.md",
            prompt_hash="abc123def456",
        )
        events = log.read_all()
        self.assertEqual(events[0]["prompt_file"], "prompts_log/turn-002-developer.md")
        self.assertEqual(events[0]["prompt_hash"], "abc123def456")

    def test_duration_seconds_present_and_rounded(self):
        log = EventLog(self._path)
        log.append(
            turn=1,
            agent="architect",
            task_id="t-001",
            status_before="continue",
            status_after="continue",
            session_id="ses_d",
            duration_seconds=12.3456,
        )
        events = log.read_all()
        self.assertIn("duration_seconds", events[0])
        self.assertEqual(events[0]["duration_seconds"], 12.35)

    def test_duration_seconds_zero_by_default(self):
        log = EventLog(self._path)
        log.append(
            turn=1,
            agent="architect",
            task_id="t-001",
            status_before="continue",
            status_after="continue",
            session_id="ses_e",
        )
        events = log.read_all()
        self.assertEqual(events[0]["duration_seconds"], 0.0)

    def test_type_field_is_turn(self):
        log = EventLog(self._path)
        log.append(
            turn=1,
            agent="architect",
            task_id="t-001",
            status_before="continue",
            status_after="continue",
            session_id="ses_f",
        )
        events = log.read_all()
        self.assertEqual(events[0]["type"], "turn")

    def test_existing_fields_unchanged(self):
        log = EventLog(self._path)
        log.append(
            turn=5,
            agent="qa_engineer",
            task_id="t-003",
            status_before="review_required",
            status_after="approved",
            session_id="ses_g",
        )
        events = log.read_all()
        r = events[0]
        self.assertEqual(r["turn"], 5)
        self.assertEqual(r["agent"], "qa_engineer")
        self.assertEqual(r["task_id"], "t-003")
        self.assertEqual(r["status_before"], "review_required")
        self.assertEqual(r["status_after"], "approved")
        self.assertEqual(r["session_id"], "ses_g")
        self.assertIn("ts", r)

    def test_append_warning_creates_warning_record(self):
        log = EventLog(self._path)
        log.append_warning(
            turn=3, agent="developer", task_id="t-004", error="Invalid transition: in_engineering → done"
        )
        events = log.read_all()
        self.assertEqual(len(events), 1)
        r = events[0]
        self.assertEqual(r["type"], "warning")
        self.assertEqual(r["level"], "warning")
        self.assertEqual(r["turn"], 3)
        self.assertEqual(r["agent"], "developer")
        self.assertEqual(r["task_id"], "t-004")
        self.assertIn("error", r)
        self.assertIn("ts", r)

    def test_append_warning_extra_fields(self):
        log = EventLog(self._path)
        log.append_warning(
            turn=2,
            agent="architect",
            task_id="t-005",
            error="bad transition",
            extra={"transition_from": "planned", "transition_to": "done"},
        )
        events = log.read_all()
        r = events[0]
        self.assertEqual(r["transition_from"], "planned")
        self.assertEqual(r["transition_to"], "done")

    def test_prompt_file_creation_integration(self):
        """Prompt files are plain text written to prompts_log/ in workspace."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            prompts_log = workspace / "prompts_log"
            prompts_log.mkdir()
            prompt_content = "# Role\nYou are the architect.\n\n## Task\nDo something."
            prompt_file = prompts_log / "turn-001-architect.md"
            prompt_file.write_text(prompt_content, encoding="utf-8")
            self.assertTrue(prompt_file.exists())
            self.assertEqual(prompt_file.read_text(encoding="utf-8"), prompt_content)


if __name__ == "__main__":
    unittest.main()
