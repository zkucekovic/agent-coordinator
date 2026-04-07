"""Unit tests for agent_coordinator/infrastructure/diagnostic_log.py"""
import importlib
import logging
import unittest
from pathlib import Path


class TestDiagnosticLog(unittest.TestCase):
    """Tests are isolated by reloading the module in setUp to reset global state."""

    def setUp(self):
        import agent_coordinator.infrastructure.diagnostic_log as mod
        # Reset module globals so tests are independent
        mod._logger = None
        mod._log_path = None
        self.mod = mod

    def test_setup_returns_path_ending_in_log(self):
        import tempfile, os
        tmp = Path(tempfile.mkdtemp())
        try:
            result = self.mod.setup(tmp)
            self.assertIsInstance(result, Path)
            self.assertTrue(str(result).endswith(".coordinator-debug.log"))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_get_logger_returns_logger_after_setup(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            self.mod.setup(tmp)
            logger = self.mod.get_logger()
            self.assertIsInstance(logger, logging.Logger)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_log_message_appears_in_file(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            log_file = self.mod.setup(tmp)
            logger = self.mod.get_logger()
            logger.info("test_message_marker_xyz")
            # Flush handlers
            for h in logger.handlers:
                h.flush()
            content = log_file.read_text(encoding="utf-8")
            self.assertIn("test_message_marker_xyz", content)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_log_crash_writes_critical_entry(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            log_file = self.mod.setup(tmp)
            self.mod.log_crash(ValueError("boom"), context="test")
            logger = self.mod.get_logger()
            for h in logger.handlers:
                h.flush()
            content = log_file.read_text(encoding="utf-8")
            self.assertIn("CRITICAL", content)
            self.assertIn("boom", content)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_log_path_returns_setup_path(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            expected = self.mod.setup(tmp)
            self.assertEqual(self.mod.log_path(), expected)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_get_logger_before_setup_does_not_crash(self):
        # _logger is None at this point (reset in setUp)
        logger = self.mod.get_logger()
        self.assertIsInstance(logger, logging.Logger)


if __name__ == "__main__":
    unittest.main()
