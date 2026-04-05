"""Tests for src.infrastructure.session_store (SessionStore)."""

import os
import tempfile
import unittest
from pathlib import Path

from agent_coordinator.infrastructure.session_store import SessionStore


def _tmp_path() -> Path:
    return Path(tempfile.gettempdir()) / f"sessions_test_{os.getpid()}.json"


class TestSessionStore(unittest.TestCase):

    def setUp(self):
        self._path = _tmp_path()

    def tearDown(self):
        if self._path.exists():
            self._path.unlink()

    def test_get_returns_none_for_unknown_agent(self):
        store = SessionStore(self._path)
        self.assertIsNone(store.get("architect"))

    def test_set_and_get_roundtrip(self):
        store = SessionStore(self._path)
        store.set("architect", "ses_abc123")
        self.assertEqual(store.get("architect"), "ses_abc123")

    def test_set_persists_to_disk(self):
        store = SessionStore(self._path)
        store.set("engineer", "ses_xyz")
        store2 = SessionStore(self._path)
        self.assertEqual(store2.get("engineer"), "ses_xyz")

    def test_set_overwrites_existing(self):
        store = SessionStore(self._path)
        store.set("architect", "ses_old")
        store.set("architect", "ses_new")
        self.assertEqual(store.get("architect"), "ses_new")

    def test_clear_removes_all_sessions(self):
        store = SessionStore(self._path)
        store.set("architect", "ses_a")
        store.set("engineer", "ses_b")
        store.clear()
        self.assertIsNone(store.get("architect"))
        self.assertIsNone(store.get("engineer"))

    def test_clear_deletes_backing_file(self):
        store = SessionStore(self._path)
        store.set("architect", "ses_a")
        store.clear()
        self.assertFalse(self._path.exists())

    def test_all_returns_copy_of_sessions(self):
        store = SessionStore(self._path)
        store.set("architect", "ses_a")
        store.set("qa", "ses_q")
        result = store.all()
        self.assertEqual(result, {"architect": "ses_a", "qa": "ses_q"})

    def test_missing_file_starts_empty(self):
        store = SessionStore(self._path)  # file doesn't exist yet
        self.assertEqual(store.all(), {})


if __name__ == "__main__":
    unittest.main()
