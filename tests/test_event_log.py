"""Tests for src.infrastructure.event_log (EventLog)."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from src.infrastructure.event_log import EventLog


class TestEventLog(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            suffix=".jsonl", delete=False, dir=tempfile.gettempdir()
        )
        self._tmp.close()
        self._path = Path(self._tmp.name)

    def tearDown(self):
        os.unlink(self._path)

    def test_append_writes_valid_json_line(self):
        log = EventLog(self._path)
        log.append(
            turn=1, agent="architect", task_id="t-001",
            status_before="continue", status_after="continue",
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
            log.append(turn=i + 1, agent="engineer", task_id="t-001",
                       status_before="continue", status_after="review_required",
                       session_id="ses_x")
        events = log.read_all()
        self.assertEqual(len(events), 3)
        self.assertEqual([e["turn"] for e in events], [1, 2, 3])

    def test_extra_fields_included(self):
        log = EventLog(self._path)
        log.append(turn=1, agent="qa", task_id="t-002",
                   status_before="continue", status_after="review_required",
                   session_id="ses_y", extra={"cost_usd": 0.003})
        events = log.read_all()
        self.assertIn("cost_usd", events[0])

    def test_read_all_on_empty_file_returns_empty_list(self):
        empty_path = Path(self._path.parent / "nonexistent.jsonl")
        log = EventLog(empty_path)
        self.assertEqual(log.read_all(), [])

    def test_each_record_has_timestamp(self):
        log = EventLog(self._path)
        log.append(turn=1, agent="architect", task_id="t-001",
                   status_before="continue", status_after="continue",
                   session_id="ses_z")
        events = log.read_all()
        self.assertIn("ts", events[0])


if __name__ == "__main__":
    unittest.main()
