"""HandoffReader — reads and parses handoff.md from disk.

Wraps the pure handoff_parser so the coordinator never touches raw file I/O
or regex directly.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.models import HandoffMessage
from src.handoff_parser import extract_latest


class HandoffReader:
    """Reads the latest valid handoff block from a handoff.md file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> HandoffMessage | None:
        """
        Parse and return the latest valid HandoffMessage.
        Returns None if the file has no valid blocks.
        """
        content = self._path.read_text(encoding="utf-8")
        message, _ = extract_latest(content)
        return message

    def read_raw(self) -> str:
        """Return the full raw text of handoff.md."""
        return self._path.read_text(encoding="utf-8")
