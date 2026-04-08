"""Tests for src.domain.retry_policy."""

import unittest

from agent_coordinator.domain.retry_policy import RetryPolicy


class TestRetryPolicy(unittest.TestCase):
    def test_default_values(self):
        p = RetryPolicy()
        self.assertEqual(p.max_rework, 3)
        self.assertEqual(p.on_exceed, "needs_human")

    def test_not_exceeded_below_limit(self):
        p = RetryPolicy(max_rework=3)
        self.assertFalse(p.is_exceeded(0))
        self.assertFalse(p.is_exceeded(2))

    def test_exceeded_at_limit(self):
        p = RetryPolicy(max_rework=3)
        self.assertTrue(p.is_exceeded(3))
        self.assertTrue(p.is_exceeded(5))

    def test_unlimited_never_exceeded(self):
        p = RetryPolicy.unlimited()
        self.assertFalse(p.is_exceeded(0))
        self.assertFalse(p.is_exceeded(100))

    def test_invalid_on_exceed_raises(self):
        with self.assertRaises(ValueError):
            RetryPolicy(on_exceed="delete_everything")

    def test_negative_max_rework_raises(self):
        with self.assertRaises(ValueError):
            RetryPolicy(max_rework=-1)

    def test_from_dict(self):
        p = RetryPolicy.from_dict({"max_rework": 5, "on_exceed": "blocked"})
        self.assertEqual(p.max_rework, 5)
        self.assertEqual(p.on_exceed, "blocked")

    def test_from_dict_uses_defaults_for_missing_keys(self):
        p = RetryPolicy.from_dict({})
        self.assertEqual(p.max_rework, 3)
        self.assertEqual(p.on_exceed, "needs_human")


if __name__ == "__main__":
    unittest.main()
