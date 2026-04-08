"""Enhanced input with readline support for better UX.

Provides:
- Command history
- Ctrl+A, Ctrl+E, Ctrl+K, Ctrl+W, etc.
- Arrow key navigation
- Tab completion
- Color prompts (if supported)
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Callable
from pathlib import Path

# Import readline for enhanced input
try:
    import readline

    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False


class EnhancedInput:
    """Enhanced input with readline support and history."""

    def __init__(self, history_file: Path | None = None):
        """
        Initialize enhanced input.

        Args:
            history_file: Optional path to save command history
        """
        self.history_file = history_file
        self._setup_readline()

    def _setup_readline(self) -> None:
        """Configure readline with history and defaults."""
        if not READLINE_AVAILABLE:
            return

        # Enable tab completion
        readline.parse_and_bind("tab: complete")

        # Vi or Emacs mode (default is Emacs)
        # readline.parse_and_bind("set editing-mode vi")  # Uncomment for vi mode

        # Load history if file exists
        if self.history_file and self.history_file.exists():
            with contextlib.suppress(Exception):
                readline.read_history_file(str(self.history_file))

        # Set history length
        if hasattr(readline, "set_history_length"):
            readline.set_history_length(1000)

    def save_history(self) -> None:
        """Save command history to file."""
        if not READLINE_AVAILABLE or not self.history_file:
            return

        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            readline.write_history_file(str(self.history_file))
        except Exception:
            pass

    def input(
        self, prompt: str = "", default: str = "", completer: Callable[[str, int], str | None] | None = None
    ) -> str:
        """
        Enhanced input with readline support.

        Args:
            prompt: Prompt to display
            default: Default value (pre-filled)
            completer: Optional tab completion function

        Returns:
            User input string
        """
        if not READLINE_AVAILABLE:
            return input(prompt)

        # Set up completer if provided
        if completer:
            readline.set_completer(completer)

        # Pre-fill with default value
        if default:

            def hook():
                readline.insert_text(default)
                readline.redisplay()

            readline.set_pre_input_hook(hook)

        try:
            result = input(prompt)
            self.save_history()
            return result
        finally:
            # Clean up
            if default:
                readline.set_pre_input_hook(None)
            if completer:
                readline.set_completer(None)

    def choice(self, prompt: str, choices: list[str], default: str | None = None) -> str:
        """
        Get choice from user with tab completion.

        Args:
            prompt: Prompt to display
            choices: Valid choices
            default: Default choice

        Returns:
            Selected choice
        """

        # Create completer for choices
        def completer(text: str, state: int) -> str | None:
            matches = [c for c in choices if c.startswith(text.lower())]
            if state < len(matches):
                return matches[state]
            return None

        while True:
            result = self.input(prompt=prompt, default=default or "", completer=completer).strip().lower()

            if result in choices:
                return result

            print(f"Invalid choice. Choose from: {', '.join(choices)}")

    def multiline(self, prompt: str = "Enter text (empty line to finish):", line_prompt: str = "> ") -> str:
        """
        Get multi-line input.

        Args:
            prompt: Initial prompt
            line_prompt: Prompt for each line

        Returns:
            Multi-line string
        """
        if prompt:
            print(prompt)

        lines = []
        while True:
            try:
                line = self.input(line_prompt)
                if not line:
                    break
                lines.append(line)
            except (EOFError, KeyboardInterrupt):
                break

        return "\n".join(lines)


# Global instance for convenience
_global_input: EnhancedInput | None = None


def get_input() -> EnhancedInput:
    """Get or create global EnhancedInput instance."""
    global _global_input  # noqa: PLW0603
    if _global_input is None:
        # Store history in user's home directory
        history_file = Path.home() / ".agent_coordinator_history"
        _global_input = EnhancedInput(history_file)
    return _global_input


def enhanced_input(prompt: str = "", default: str = "") -> str:
    """
    Convenience function for enhanced input.

    Supports all readline features:
    - Ctrl+A: Move to beginning
    - Ctrl+E: Move to end
    - Ctrl+K: Kill to end
    - Ctrl+W: Delete word backward
    - Ctrl+U: Delete to beginning
    - Arrow keys: Navigate
    - Up/Down: History
    """
    return get_input().input(prompt, default)


def enhanced_choice(prompt: str, choices: list[str], default: str | None = None) -> str:
    """
    Convenience function for choice with tab completion.

    Example:
        choice = enhanced_choice("Action: ", ["continue", "quit", "retry"])
    """
    return get_input().choice(prompt, choices, default)


def enhanced_multiline(prompt: str = "", line_prompt: str = "> ") -> str:
    """
    Convenience function for multi-line input.

    Each line supports full readline editing.
    """
    return get_input().multiline(prompt, line_prompt)


# Terminal colors (if supported)
class Colors:
    """ANSI color codes."""

    @staticmethod
    def _supports_color() -> bool:
        """Check if terminal supports color."""
        if not sys.stdout.isatty():
            return False
        if os.environ.get("NO_COLOR"):
            return False
        return os.environ.get("TERM") != "dumb"

    ENABLED = _supports_color()

    # Colors
    RESET = "\033[0m" if ENABLED else ""
    BOLD = "\033[1m" if ENABLED else ""
    DIM = "\033[2m" if ENABLED else ""

    # Foreground
    BLACK = "\033[30m" if ENABLED else ""
    RED = "\033[31m" if ENABLED else ""
    GREEN = "\033[32m" if ENABLED else ""
    YELLOW = "\033[33m" if ENABLED else ""
    BLUE = "\033[34m" if ENABLED else ""
    MAGENTA = "\033[35m" if ENABLED else ""
    CYAN = "\033[36m" if ENABLED else ""
    WHITE = "\033[37m" if ENABLED else ""

    @classmethod
    def colorize(cls, text: str, color: str) -> str:
        """Colorize text if colors are enabled."""
        if not cls.ENABLED:
            return text
        return f"{color}{text}{cls.RESET}"

    @classmethod
    def prompt(cls, text: str) -> str:
        """Format a prompt with color."""
        return cls.colorize(text, cls.CYAN + cls.BOLD)

    @classmethod
    def success(cls, text: str) -> str:
        """Format success message."""
        return cls.colorize(text, cls.GREEN)

    @classmethod
    def error(cls, text: str) -> str:
        """Format error message."""
        return cls.colorize(text, cls.RED)

    @classmethod
    def warning(cls, text: str) -> str:
        """Format warning message."""
        return cls.colorize(text, cls.YELLOW)

    @classmethod
    def info(cls, text: str) -> str:
        """Format info message."""
        return cls.colorize(text, cls.BLUE)
