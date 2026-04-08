"""Enhanced output display for better agent work observability.

Provides real-time visual feedback of agent activity with reserved display space.
"""

from __future__ import annotations

import shutil
import sys
import threading
import time
import typing
from typing import TextIO


class ThinkingIndicator:
    """Animated thinking indicator while agent is working."""

    FRAMES: typing.ClassVar[list[str]] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, stream: TextIO = sys.stdout):
        self.stream = stream
        self.running = False
        self.thread: threading.Thread | None = None

    def start(self, message: str = "Thinking") -> None:
        """Start the animated indicator."""
        if not self.stream.isatty():
            # Non-TTY: just print once
            self.stream.write(f"{message}...\n")
            self.stream.flush()
            return

        self.running = True
        self.thread = threading.Thread(target=self._animate, args=(message,))
        self.thread.daemon = True
        self.thread.start()

    def stop(self) -> None:
        """Stop the animated indicator."""
        if not self.running:
            return

        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)

        # Clear the line
        if self.stream.isatty():
            self.stream.write("\r\033[K")
            self.stream.flush()

    def _animate(self, message: str) -> None:
        """Animation loop."""
        idx = 0
        while self.running:
            frame = self.FRAMES[idx % len(self.FRAMES)]
            self.stream.write(f"\r{frame} {message}...")
            self.stream.flush()
            time.sleep(0.1)
            idx += 1


class AgentOutputDisplay:
    """Manages enhanced display of agent output with reserved lines."""

    def __init__(self, reserved_lines: int = 10, stream: TextIO = sys.stdout):
        self.reserved_lines = reserved_lines
        self.stream = stream
        self.current_buffer: list[str] = []
        self.is_active = False
        self.thinking = ThinkingIndicator(stream)

    def start_agent_turn(self, agent: str, backend: str, task_id: str, status: str) -> None:
        """Initialize the display area for an agent's turn."""
        self.is_active = True
        self.current_buffer = []

        # Print header
        terminal_width = shutil.get_terminal_size().columns
        self._print(f"\n{'═' * terminal_width}")
        self._print(f"🤖 Agent: {agent.upper()}")
        self._print(f"   Backend: {backend}")
        self._print(f"   Task: {task_id}")
        self._print(f"   Status: {status}")
        self._print(f"{'─' * terminal_width}")
        self._print("")

        # Start thinking animation
        self.thinking.start(f"💭 {agent} is thinking")

    def update_output(self, text: str) -> None:
        """Update the display with new output."""
        # Stop thinking animation on first output
        if self.thinking.running:
            self.thinking.stop()

        if not self.is_active:
            self._print(text, end="", flush=True)
            return

        # Just print the output directly - no reserved lines needed
        # since most backends don't stream
        self._print(text, end="", flush=True)

    def finish_agent_turn(self, success: bool, new_status: str = "", next_agent: str = "") -> None:
        """Finalize the display after agent completes."""
        # Stop thinking animation
        self.thinking.stop()

        if not self.is_active:
            return

        terminal_width = shutil.get_terminal_size().columns
        self._print(f"\n{'─' * terminal_width}")

        if success:
            self._print("✅ Turn completed successfully")
            if new_status:
                self._print(f"   New status: {new_status}")
            if next_agent:
                self._print(f"   Next agent: {next_agent}")
        else:
            self._print("❌ Turn failed or incomplete")

        self._print(f"{'═' * terminal_width}\n")

        self.is_active = False
        self.current_buffer = []

    def _print(self, text: str = "", end: str = "\n", flush: bool = True) -> None:
        """Print to stream."""
        self.stream.write(text + end)
        if flush:
            self.stream.flush()

    def _move_cursor_up(self, lines: int) -> None:
        """Move cursor up N lines."""
        if lines > 0:
            self.stream.write(f"\033[{lines}A")
            self.stream.flush()

    def _move_cursor_down(self, lines: int) -> None:
        """Move cursor down N lines."""
        if lines > 0:
            self.stream.write(f"\033[{lines}B")
            self.stream.flush()

    def _clear_reserved_area(self) -> None:
        """Clear the reserved display area."""
        for _ in range(self.reserved_lines):
            # Clear line and move down
            self.stream.write("\033[2K\n")
        # Move back up
        self._move_cursor_up(self.reserved_lines)
        self.stream.flush()


class SimpleProgressDisplay:
    """Simplified progress display for non-TTY environments."""

    def __init__(self, stream: TextIO = sys.stdout):
        self.stream = stream
        self.thinking = ThinkingIndicator(stream)

    def start_agent_turn(self, agent: str, backend: str, task_id: str, status: str) -> None:
        """Start agent turn with simple header."""
        self._print(f"\n{'=' * 60}")
        self._print(f"🤖 {agent.upper()} ({backend})")
        self._print(f"   Task: {task_id} | Status: {status}")
        self._print(f"{'─' * 60}")
        self.thinking.start(f"💭 {agent} is working")

    def update_output(self, text: str) -> None:
        """Stream output directly."""
        # Stop thinking animation on first output
        if self.thinking.running:
            self.thinking.stop()
        self._print(text, end="", flush=True)

    def finish_agent_turn(self, success: bool, new_status: str = "", next_agent: str = "") -> None:
        """Finish turn with summary."""
        self.thinking.stop()
        self._print(f"\n{'─' * 60}")
        if success:
            self._print("✅ Completed")
            if new_status:
                self._print(f"   New status: {new_status}")
            if next_agent:
                self._print(f"   Next: {next_agent}")
        else:
            self._print("❌ Failed")
        self._print(f"{'=' * 60}\n")

    def _print(self, text: str = "", end: str = "\n", flush: bool = True) -> None:
        """Print to stream."""
        self.stream.write(text + end)
        if flush:
            self.stream.flush()


def create_display(reserved_lines: int = 10, force_simple: bool = False) -> AgentOutputDisplay | SimpleProgressDisplay:
    """
    Create appropriate display based on terminal capabilities.

    Args:
        reserved_lines: Number of lines to reserve for agent output
        force_simple: Force simple display even in TTY

    Returns:
        Display instance appropriate for the environment
    """
    # Check if we're in a TTY
    if not force_simple and sys.stdout.isatty():
        return AgentOutputDisplay(reserved_lines=reserved_lines)
    else:
        return SimpleProgressDisplay()
