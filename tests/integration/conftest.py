"""
Shared helpers for integration tests.

Skip everything unless RUN_INTEGRATION_TESTS=1 is set in the environment.
Real opencode calls cost tokens — guard behind the env-var gate.

Usage:
    RUN_INTEGRATION_TESTS=1 python3 -m unittest discover tests/integration/ -v
"""

import os
import unittest

#: Module-level skip guard — add to every integration TestCase.
requires_integration = unittest.skipUnless(
    os.environ.get("RUN_INTEGRATION_TESTS") == "1",
    "Set RUN_INTEGRATION_TESTS=1 to run integration tests (uses real opencode)",
)
