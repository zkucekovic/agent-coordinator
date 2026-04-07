#!/usr/bin/env python3
"""
coordinator.py — backwards-compatible entry point.

If you installed via pip, use `agent-coordinator` instead.
If you cloned the repo, `python3 coordinator.py` still works.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Support both installed package and git-clone usage.
sys.path.insert(0, str(Path(__file__).parent))
from agent_coordinator.cli import main

if __name__ == "__main__":
    main()
