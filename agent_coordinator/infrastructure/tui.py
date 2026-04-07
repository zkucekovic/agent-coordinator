"""TUI interface for agent coordinator.

Implements a proper alternate-screen terminal UI with a pinned status bar,
modelled after nano/vim.  Falls back to SimpleProgressDisplay when not a TTY.

Public API (unchanged from previous versions so cli.py needs no edits):

    display = create_display()
    display.start_run(agents, workspace, max_turns)   # call once before loop
    display.start_agent_turn(agent, backend, task_id, status)
    display.update_output(text)                        # can be called many times
    display.finish_agent_turn(success, new_status, next_agent)
    display.close()                                    # restore terminal

    menu = InterruptMenu(display)
    choice = menu.show()

    popup = Popup(display)                             # reusable modal dialog
    choice = popup.show(title="…", body="…", options=[("r", "Run")])

Layout (inside alternate screen)
─────────────────────────────────
  row 1          : top header bar  (static)
  rows 2 .. R-2  : scrolling content area
  row R-1        : separator
  row R          : pinned status bar  ← never scrolls
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import sys
import threading
import time
from enum import Enum
from typing import Callable, TextIO

try:
    import termios
    import tty
    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False   # Windows / unusual environments


# ── ANSI helpers ──────────────────────────────────────────────────────────────

ESC = "\033"
_ANSI_RE = re.compile(r"\033\[[0-9;]*[mGKHJABCDsuhr]|\033\[[?][0-9]*[hl]")

def _csi(*parts: str) -> str:
    return ESC + "[" + "".join(parts)

# Cursor movement
def _cup(row: int, col: int = 1) -> str:   return _csi(f"{row};{col}H")
def _el()  -> str:                          return _csi("2K")          # erase line
def _ed()  -> str:                          return _csi("J")           # erase to end of screen
def _sc()  -> str:                          return ESC + "7"           # save cursor (DEC)
def _rc()  -> str:                          return ESC + "8"           # restore cursor

# Alternate screen
_ALT_ENTER  = _csi("?1049h")
_ALT_EXIT   = _csi("?1049l")
_HIDE_CURSOR = _csi("?25l")
_SHOW_CURSOR = _csi("?25h")

# Colors / styles
_RESET  = _csi("0m")
_BOLD   = _csi("1m")
_DIM    = _csi("2m")

def _tc(r: int, g: int, b: int) -> str: return _csi(f"38;2;{r};{g};{b}m")   # true-color fg
def _bc(r: int, g: int, b: int) -> str: return _csi(f"48;2;{r};{g};{b}m")   # true-color bg

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# ── Theme ─────────────────────────────────────────────────────────────────────

class Theme:
    """
    All colors used by the TUI.  Override any attribute to customise.

    Colors are ANSI escape strings produced by _tc() / _bc().
    Background colors use _bc(); foreground colors use _tc().
    """

    def __init__(
        self,
        name: str,
        # Status / header bars
        bg_header:    str,
        bg_status:    str,
        bg_separator: str,
        # Agent LED states
        led_running:  str,   # ● blinking — agent active
        led_done:     str,   # ● steady   — finished last turn, idle now
        led_error:    str,   # ● steady
        led_blocked:  str,   # ● steady
        led_idle:     str,   # ○ — never ran
        # Text
        text_primary:   str,
        text_secondary: str,
        text_dim:       str,
        # Syntax
        color_agent:    str,   # agent name in turn headers
        color_success:  str,   # ✓ markers
        color_warning:  str,   # ✗ / warnings
        color_info:     str,   # info lines
    ) -> None:
        self.name         = name
        self.bg_header    = bg_header
        self.bg_status    = bg_status
        self.bg_separator = bg_separator
        self.led_running  = led_running
        self.led_done     = led_done
        self.led_error    = led_error
        self.led_blocked  = led_blocked
        self.led_idle     = led_idle
        self.text_primary   = text_primary
        self.text_secondary = text_secondary
        self.text_dim       = text_dim
        self.color_agent    = color_agent
        self.color_success  = color_success
        self.color_warning  = color_warning
        self.color_info     = color_info


# ── Built-in themes ───────────────────────────────────────────────────────────

def _catppuccin_frappe() -> Theme:
    """Catppuccin Frappé — https://github.com/catppuccin/catppuccin"""
    return Theme(
        name          = "catppuccin-frappe",
        bg_header     = _bc(41,  44,  60),   # Mantle  #292c3c
        bg_status     = _bc(35,  38,  52),   # Crust   #232634
        bg_separator  = _bc(65,  69,  89),   # Surface1 #414559 — slightly lighter
        led_running   = _tc(166, 209, 137),  # Green   #a6d189
        led_done      = _tc(131, 139, 167),  # Overlay1 #838ba7 — neutral, not green
        led_error     = _tc(231, 130, 132),  # Red     #e78284
        led_blocked   = _tc(229, 200, 144),  # Yellow  #e5c890
        led_idle      = _tc(115, 121, 148),  # Overlay0 #737994
        text_primary  = _tc(198, 208, 245),  # Text    #c6d0f5
        text_secondary= _tc(165, 173, 206),  # Subtext0 #a5adce
        text_dim      = _tc(115, 121, 148),  # Overlay0 #737994
        color_agent   = _tc(140, 170, 238),  # Blue    #8caaee
        color_success = _tc(166, 209, 137),  # Green   #a6d189
        color_warning = _tc(239, 159, 118),  # Peach   #ef9f76
        color_info    = _tc(133, 193, 220),  # Sapphire #85c1dc
    )


def _dark_default() -> Theme:
    """Classic dark theme (original hardcoded palette)."""
    g = lambda n: _csi(f"38;5;{n}m")
    b = lambda n: _csi(f"48;5;{n}m")
    return Theme(
        name          = "dark",
        bg_header     = b(235),
        bg_status     = b(236),
        bg_separator  = b(238),
        led_running   = g(46),    # bright green
        led_done      = g(240),   # dim gray — not green when idle
        led_error     = g(196),   # red
        led_blocked   = g(226),   # yellow
        led_idle      = g(238),   # very dim gray
        text_primary  = g(255),
        text_secondary= g(245),
        text_dim      = g(240),
        color_agent   = g(87),    # cyan
        color_success = g(46),
        color_warning = g(214),
        color_info    = g(33),
    )


_THEMES: dict[str, Theme] = {
    "catppuccin-frappe": _catppuccin_frappe(),
    "dark":              _dark_default(),
}

DEFAULT_THEME_NAME = "catppuccin-frappe"


def get_theme(name: str | None = None) -> Theme:
    """Return a theme by name, falling back to the default."""
    return _THEMES.get(name or DEFAULT_THEME_NAME, _catppuccin_frappe())


# ── Agent state ───────────────────────────────────────────────────────────────

class AgentState(Enum):
    IDLE    = "idle"
    RUNNING = "running"
    DONE    = "done"     # finished last turn — control passed to another agent
    ERROR   = "error"
    BLOCKED = "blocked"

_STATE_DOT = {
    AgentState.IDLE:    "○",
    AgentState.RUNNING: "●",
    AgentState.DONE:    "●",
    AgentState.ERROR:   "●",
    AgentState.BLOCKED: "●",
}

def _state_color(state: AgentState, theme: Theme) -> str:
    return {
        AgentState.IDLE:    theme.led_idle,
        AgentState.RUNNING: theme.led_running,
        AgentState.DONE:    theme.led_done,
        AgentState.ERROR:   theme.led_error,
        AgentState.BLOCKED: theme.led_blocked,
    }[state]


# ── Popup ─────────────────────────────────────────────────────────────────────

class Popup:
    """Reusable centered modal popup for the alt-screen TUI.

    Handles all box-drawing alignment math in one place.  Supports two
    layout modes that can be combined:

    * **options** – horizontal flow-wrapped key/label pairs
      (like the error-recovery dialog)
    * **items** – vertical one-per-row entries with separator support
      (like the Ctrl+C interrupt menu)

    Usage::

        popup = Popup(screen)
        choice = popup.show(
            title="AGENT COORDINATOR",
            icon="▶",
            body="Workspace: examples",
            options=[("r", "Run"), ("q", "Quit")],
        )
    """

    def __init__(self, screen: "Screen") -> None:
        self._scr = screen

    # ── Public ────────────────────────────────────────────────────────────────

    def show(
        self,
        *,
        title: str,
        icon: str = "",
        body: str | list[str] = "",
        options: list[tuple[str, str]] | None = None,
        items: list[tuple[str, str] | None] | None = None,
        title_color: str | None = None,
    ) -> str:
        """Render a centered popup, wait for a keypress, erase, and return it.

        Parameters
        ----------
        title : str
            Text shown in the title bar.
        icon : str
            Single character drawn before the title (e.g. "▶", "⚠").
        body : str | list[str]
            Message shown below the title.  A string is word-wrapped; a list
            is used as-is.
        options : list of (key, label)
            Horizontal flow-wrapped option bar at the bottom.
        items : list of (key, label) | None
            Vertical menu items.  ``None`` entries become separator lines.
        title_color : str | None
            ANSI color sequence for the title.  Defaults to theme.color_warning.
        """
        scr = self._scr
        t = scr._theme
        if title_color is None:
            title_color = t.color_warning

        if not scr._active:
            return self._show_plain(title, body, options, items)

        cap_w = min(scr._cols - 4, 72)
        cap_inner = cap_w - 2

        # -- Prepare body lines ------------------------------------------------
        if isinstance(body, str) and body:
            body_lines = _wrap_text(body, cap_inner - 2)
        elif isinstance(body, list):
            body_lines = body
        else:
            body_lines = []

        # -- Measure content widths to auto-size the box -----------------------
        icon_str = f"{icon}  " if icon else ""
        title_text = f"{icon_str}{title}"
        widths: list[int] = [len(title_text)]
        for line in body_lines:
            widths.append(len(_strip_ansi(line)))

        valid_keys: set[str] = set()

        # -- Prepare menu items (vertical, one per row) ------------------------
        item_rows: list[tuple[str, str] | None] = []
        if items:
            for entry in items:
                if entry is None:
                    item_rows.append(None)
                else:
                    item_rows.append(entry)
                    valid_keys.add(entry[0].lower())
                    k_display = entry[0] if entry[0].startswith("/") else f"[{entry[0]}]"
                    widths.append(len(f"  {k_display}  {entry[1]}"))

        # -- Prepare option rows (horizontal, flow-wrapped) --------------------
        # We need inner_w first to compute wrapping, so compute preliminary
        inner_w = min(max(w + 1 for w in widths), cap_inner)

        opt_rows: list[list[tuple[str, str]]] = []

        if options:
            opt_rows.append([])
            row_len = 0
            for k, label in options:
                valid_keys.add(k.lower())
                part_len = len(f"[{k}] {label}  ")
                if opt_rows[-1] and row_len + part_len > inner_w - 1:
                    opt_rows.append([])
                    row_len = 0
                opt_rows[-1].append((k, label))
                row_len += part_len
            # Add option row widths
            for orow in opt_rows:
                widths.append(sum(len(f"[{k}] {label}  ") for k, label in orow))

        # Final inner_w: fit widest content + 1 char padding, capped
        inner_w = min(max(w + 1 for w in widths), cap_inner)
        max_w = inner_w + 2

        # Re-wrap options with final inner_w
        if options:
            opt_rows = [[]]
            row_len = 0
            for k, label in options:
                part_len = len(f"[{k}] {label}  ")
                if opt_rows[-1] and row_len + part_len > inner_w - 1:
                    opt_rows.append([])
                    row_len = 0
                opt_rows[-1].append((k, label))
                row_len += part_len

        # -- Compute box height ------------------------------------------------
        h = 3  # top border + title row + separator
        h += len(body_lines) if body_lines else 0
        if body_lines and (opt_rows or item_rows):
            h += 1  # separator between body and items/options
        h += len(item_rows)
        h += len(opt_rows)
        h += 1  # bottom border

        # -- Center on screen --------------------------------------------------
        row0 = max(2, (scr._rows - h) // 2)
        col0 = max(1, (scr._cols - max_w) // 2)

        # -- Render ------------------------------------------------------------
        buf: list[str] = [_sc()]
        row = row0

        # Helpers — each produces exactly max_w visible characters
        def hline(left: str, fill: str, right: str, color: str = t.text_dim) -> str:
            return (_cup(row, col0) + t.bg_status + color
                    + left + fill * inner_w + right + _RESET)

        def content_row(text: str, *, color: str = t.text_primary,
                        ansi_text: str | None = None) -> str:
            """Render │ text ... │ with correct padding.

            If *ansi_text* is given it is printed instead of *text*, but
            *text* is used to measure visible width.
            """
            display = ansi_text if ansi_text is not None else text
            pad = max(0, inner_w - 1 - len(text))
            return (_cup(row, col0) + t.bg_status + color
                    + "│ " + display + " " * pad + "│" + _RESET)

        # Top border
        buf.append(hline("┌", "─", "┐", title_color + _BOLD))
        row += 1

        # Title
        buf.append(content_row(title_text, color=title_color + _BOLD))
        row += 1

        # Separator after title
        buf.append(hline("├", "─", "┤"))
        row += 1

        # Body
        for line in body_lines:
            vis = _strip_ansi(line)
            buf.append(content_row(vis, ansi_text=line))
            row += 1

        # Separator between body and options/items
        if body_lines and (opt_rows or item_rows):
            buf.append(hline("├", "─", "┤"))
            row += 1

        # Vertical menu items
        for entry in item_rows:
            if entry is None:
                buf.append(hline("├", "─", "┤"))
                row += 1
                continue
            key, desc = entry
            k_display = key if key.startswith("/") else f"[{key}]"
            k_styled = t.color_success + _BOLD + k_display + _RESET
            plain = f"  {k_display}  {desc}"
            ansi = f"  {k_styled}  {t.text_secondary}{desc}{_RESET}"
            buf.append(content_row(plain, ansi_text=ansi))
            row += 1

        # Horizontal option rows
        for orow in opt_rows:
            plain = "".join(f"[{k}] {label}  " for k, label in orow)
            ansi = "".join(
                f"{t.color_agent}[{k}]{_RESET}{t.text_primary} {label}  "
                for k, label in orow
            )
            buf.append(content_row(plain, ansi_text=ansi))
            row += 1

        # Bottom border
        buf.append(hline("└", "─", "┘"))

        scr._write("".join(buf))

        # -- Read keypress -----------------------------------------------------
        choice = ""
        while choice not in valid_keys:
            try:
                ch = sys.stdin.read(1)
                choice = ch.lower()
            except (EOFError, OSError):
                # fall back to last option
                if options:
                    choice = options[-1][0]
                elif items:
                    last = [e for e in items if e is not None]
                    choice = last[-1][0].lower() if last else "q"
                else:
                    choice = "q"
                break

        # -- Erase popup -------------------------------------------------------
        erase: list[str] = []
        for r in range(row0, row + 1):
            erase.append(_cup(r, col0) + " " * max_w)
        erase.append(_rc())
        scr._write("".join(erase))
        scr._full_render()
        return choice

    # ── Plain-text fallback (non-TTY / alt-screen not active) ─────────────────

    @staticmethod
    def _show_plain(
        title: str,
        body: str | list[str],
        options: list[tuple[str, str]] | None,
        items: list[tuple[str, str] | None] | None,
    ) -> str:
        sys.stderr.write(f"\n{title}\n")
        if isinstance(body, str) and body:
            sys.stderr.write(f"{body}\n")
        elif isinstance(body, list):
            for line in body:
                sys.stderr.write(f"{_strip_ansi(line)}\n")
        if items:
            for entry in items:
                if entry is None:
                    sys.stderr.write("─" * 40 + "\n")
                else:
                    sys.stderr.write(f"  [{entry[0]}] {entry[1]}\n")
        if options:
            keys = "/".join(k for k, _ in options)
            sys.stderr.write(f"[{keys}]: ")
            sys.stderr.flush()
            return (input() or options[-1][0]).strip().lower()
        if items:
            valid = {e[0].lower() for e in items if e is not None}
            sys.stderr.write("Choice: ")
            sys.stderr.flush()
            try:
                ch = input().strip().lower()
                return ch if ch in valid else "q"
            except (EOFError, KeyboardInterrupt):
                return "q"
        return "q"


# ── Screen ────────────────────────────────────────────────────────────────────

class Screen:
    """
    Owns the alternate terminal screen.

    Responsibilities:
    - enter / exit alternate screen
    - maintain a ring-buffer of content lines
    - render header (row 1) and status bar (last row) without scrolling them
    - expose write() for streaming agent output into the content area
    - thread-safe: a background thread blinks the active agent dot
    """

    _HEADER_ROWS = 1   # number of rows reserved at top
    _SEP_ROWS    = 1   # separator row above status bar
    _STATUS_ROWS = 1   # pinned status bar

    _MAX_LINES = 5000  # cap content buffer to prevent unbounded memory growth

    def __init__(self, stream: TextIO = sys.stdout, theme: Theme | None = None) -> None:
        self._stream   = stream
        self._lock     = threading.Lock()
        self._theme    = theme or get_theme()
        self._lines: list[str] = []          # content ring-buffer
        self._cols  = 80
        self._rows  = 24
        self._content_rows = 20              # updated in _refresh_size

        # State tracking
        self._agents: list[str] = []
        self._agent_states: dict[str, AgentState] = {}
        self._current_agent   = ""
        self._workspace       = ""
        self._max_turns       = 0
        self._current_turn    = 0
        self._spinner_idx     = 0
        self._blink_on        = True
        self._active          = False        # are we in alt screen?

        # Animation thread
        self._anim_thread: threading.Thread | None = None
        self._anim_stop   = threading.Event()

        # Pause state
        self._paused = False

        # SIGWINCH for resize
        self._orig_sigwinch: Callable | None = None

        # Saved terminal settings (restored on close)
        self._orig_termios: list | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _stop_animation(self) -> None:
        """Stop the current animation thread if running."""
        self._anim_stop.set()
        if self._anim_thread is not None:
            self._anim_thread.join(timeout=1)
            self._anim_thread = None

    def _start_animation(self) -> None:
        """Start a new animation thread, stopping any existing one first."""
        self._stop_animation()
        self._anim_stop.clear()
        self._anim_thread = threading.Thread(target=self._animate, daemon=True)
        self._anim_thread.start()

    def start_menu(self) -> None:
        """Enter alt-screen for the startup menu (no agents, no turn counter)."""
        if not self._stream.isatty():
            return
        self._agents = []
        self._workspace = ""
        self._max_turns = 0
        self._agent_states = {}
        self._refresh_size()
        self._active = True
        if _HAS_TERMIOS and sys.stdin.isatty():
            try:
                self._orig_termios = termios.tcgetattr(sys.stdin.fileno())
                new = termios.tcgetattr(sys.stdin.fileno())
                new[3] &= ~(termios.ECHO | termios.ECHOE | termios.ECHOK | termios.ICANON)
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, new)
            except termios.error:
                self._orig_termios = None
        self._write(_ALT_ENTER + _HIDE_CURSOR)
        self._full_render()
        try:
            self._orig_sigwinch = signal.signal(signal.SIGWINCH, self._on_resize)
        except (OSError, ValueError):
            pass
        self._start_animation()

    def read_input(self, prompt: str) -> str:
        """
        Read a line of input from the user, rendered inside the alt-screen.

        Temporarily re-enables echo + canonical mode, draws the prompt at the
        bottom of the content area, reads until Enter, then re-disables.
        Returns the stripped input string, or "" on EOF/interrupt.
        """
        if not self._active:
            try:
                return input(prompt)
            except (EOFError, KeyboardInterrupt):
                return ""

        t = self._theme
        prompt_row = self._rows - self._SEP_ROWS - self._STATUS_ROWS - 1

        # Re-enable echo + canonical for a normal input read
        if _HAS_TERMIOS and self._orig_termios is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, self._orig_termios)
            except termios.error:
                pass

        self._write(_SHOW_CURSOR)
        # Draw prompt line above separator
        prompt_render = (
            _cup(prompt_row, 1)
            + t.bg_status + _el()
            + t.color_agent + _BOLD + "  ❯ " + _RESET
            + t.text_primary + prompt
        )
        self._write(prompt_render)

        try:
            value = input()
        except (EOFError, KeyboardInterrupt):
            value = ""

        # Clear prompt row and re-disable echo
        self._write(_cup(prompt_row, 1) + _el())
        self._write(_HIDE_CURSOR)
        if _HAS_TERMIOS and self._orig_termios is not None:
            try:
                new = termios.tcgetattr(sys.stdin.fileno())
                new[3] &= ~(termios.ECHO | termios.ECHOE | termios.ECHOK | termios.ICANON)
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, new)
            except termios.error:
                pass

        return value.strip()

    def start_run(
        self,
        agents: list[str],
        workspace: str,
        max_turns: int,
    ) -> None:
        """Enter alternate screen and draw the initial layout."""
        if not self._stream.isatty():
            return

        self._agents   = agents
        self._workspace = os.path.basename(workspace) or workspace
        self._max_turns = max_turns
        self._agent_states = {a: AgentState.IDLE for a in agents}

        self._refresh_size()
        self._active = True

        # Disable terminal echo + canonical mode so keystrokes don't corrupt display.
        # Keep ISIG so Ctrl+C still fires SIGINT.
        if _HAS_TERMIOS and sys.stdin.isatty():
            try:
                self._orig_termios = termios.tcgetattr(sys.stdin.fileno())
                new = termios.tcgetattr(sys.stdin.fileno())
                # c_lflag bits: clear ECHO, ECHOE, ECHOK, ICANON; keep ISIG
                new[3] &= ~(termios.ECHO | termios.ECHOE | termios.ECHOK | termios.ICANON)
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, new)
            except termios.error:
                self._orig_termios = None

        self._write(_ALT_ENTER + _HIDE_CURSOR)
        self._full_render()

        # SIGWINCH resize handler
        try:
            self._orig_sigwinch = signal.signal(signal.SIGWINCH, self._on_resize)
        except (OSError, ValueError):
            pass   # not available on Windows or non-main thread

        # Start animation thread
        self._start_animation()

    def set_paused(self, paused: bool) -> None:
        """Mark the coordinator as paused/resumed — updates header label."""
        with self._lock:
            self._paused = paused

    def with_editor(self, path: "Path | str") -> None:
        """
        Temporarily leave alt-screen, open $EDITOR on path, then re-enter.
        Safe to call from the main thread while the animation thread is running.
        """
        import subprocess
        from agent_coordinator.infrastructure.editor import get_editor

        self._anim_stop.set()
        if self._anim_thread:
            self._anim_thread.join(timeout=1)

        if _HAS_TERMIOS and self._orig_termios is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, self._orig_termios)
            except termios.error:
                pass

        self._write(_SHOW_CURSOR + _ALT_EXIT)
        try:
            subprocess.run([get_editor(), str(path)], check=True)
        except Exception:
            pass

        self._write(_ALT_ENTER + _HIDE_CURSOR)
        if _HAS_TERMIOS and self._orig_termios is not None:
            try:
                new = termios.tcgetattr(sys.stdin.fileno())
                new[3] &= ~(termios.ECHO | termios.ECHOE | termios.ECHOK | termios.ICANON)
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, new)
            except termios.error:
                pass
        self._full_render()
        self._start_animation()

    def close(self) -> None:
        """Exit alternate screen and restore terminal."""
        if not self._active:
            return

        self._stop_animation()
        try:
            if self._orig_sigwinch is not None:
                signal.signal(signal.SIGWINCH, self._orig_sigwinch)
        except (OSError, ValueError):
            pass

        self._write(_SHOW_CURSOR + _ALT_EXIT)

        # Restore terminal settings
        if _HAS_TERMIOS and self._orig_termios is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, self._orig_termios)
            except termios.error:
                pass
            self._orig_termios = None

        self._active = False
        self._lines.clear()  # free content buffer memory

    # ── Public display API (matches old TUIDisplay / AgentOutputDisplay) ───────

    # Compatibility shim — cli.py sets this attribute
    @property
    def max_output_lines(self) -> int:
        return self._content_rows

    @max_output_lines.setter
    def max_output_lines(self, value: int) -> None:
        pass   # we use the full content area; ignore the old fixed-size setting

    # Compatibility shim — cli.py sets this attribute
    @property
    def stream_delay(self) -> float:
        return 0.0

    @stream_delay.setter
    def stream_delay(self, value: float) -> None:
        pass

    # Compatibility shim — cli.py accesses display.thinking.stop()
    class _FakeThinking:
        def stop(self) -> None:
            pass
        running = False

    thinking = _FakeThinking()

    def start_agent_turn(
        self,
        agent: str,
        backend: str,
        task_id: str,
        status: str,
    ) -> None:
        t = self._theme
        self._current_agent = agent
        self._set_state(agent, AgentState.RUNNING)
        self._current_turn += 1

        sep = "─" * max(0, self._cols - 4)
        self._append_content("")
        self._append_content(
            f"{t.color_agent}{_BOLD}▸ {agent.upper()}{_RESET}  "
            f"{t.text_dim}{backend}  {task_id}  {status}{_RESET}"
        )
        self._append_content(f"{t.text_dim}{sep}{_RESET}")

    def update_output(self, text: str) -> None:
        """Stream one chunk (line or partial line) of agent output."""
        t = self._theme
        for line in text.split("\n"):
            if line:
                self._append_content(f"  {t.text_secondary}{line}{_RESET}")

    def finish_agent_turn(
        self,
        success: bool,
        new_status: str = "",
        next_agent: str = "",
    ) -> None:
        t = self._theme
        if success:
            # Agent passes control — mark as DONE (neutral, not green)
            self._set_state(self._current_agent, AgentState.DONE)
            parts = []
            if new_status:
                parts.append(f"status → {new_status}")
            if next_agent:
                parts.append(f"next → {t.color_agent}{next_agent}{_RESET}")
            self._append_content(
                f"  {t.color_success}✓{_RESET}  " + "  ".join(parts)
            )
        else:
            self._set_state(self._current_agent, AgentState.ERROR)
            self._append_content(f"  {t.color_warning}✗  Turn incomplete{_RESET}")

        self._append_content("")

    # ── Internal rendering ────────────────────────────────────────────────────

    def _refresh_size(self) -> None:
        sz = shutil.get_terminal_size()
        self._cols = sz.columns
        self._rows = sz.lines
        self._content_rows = max(
            4,
            self._rows - self._HEADER_ROWS - self._SEP_ROWS - self._STATUS_ROWS - 1,
        )

    def _full_render(self) -> None:
        """Draw the entire screen from scratch."""
        buf: list[str] = []
        buf.append(_cup(1, 1))
        buf.append(_ed())
        buf.append(self._render_header())
        # content area is drawn by _render_content
        buf.append(self._render_content_block())
        buf.append(self._render_separator())
        buf.append(self._render_status_bar())
        # park cursor in content area
        content_cursor_row = self._HEADER_ROWS + min(
            len(self._lines), self._content_rows
        ) + 1
        buf.append(_cup(content_cursor_row, 1))
        self._write("".join(buf))

    def _render_header(self) -> str:
        t = self._theme
        title = "  AGENT COORDINATOR"
        if self._paused:
            state_tag = t.color_warning + _BOLD + "  ⏸ PAUSED" + _RESET + t.bg_header + t.text_dim
        else:
            state_tag = ""
        turn_info = f"turn {self._current_turn}/{self._max_turns}  " if self._max_turns else ""
        pad = max(0, self._cols - len(title) - len(state_tag and "  ⏸ PAUSED") - len(turn_info))
        return (
            _cup(1, 1)
            + t.bg_header + t.text_primary + _BOLD
            + title
            + (state_tag if self._paused else "")
            + " " * pad
            + t.text_dim + turn_info
            + _RESET
        )

    def _render_content_block(self) -> str:
        rows_available = self._content_rows
        lines = self._lines[-rows_available:] if self._lines else []
        buf: list[str] = []
        for i, line in enumerate(lines):
            row = self._HEADER_ROWS + 1 + i
            buf.append(_cup(row, 1) + _el() + line)
        for i in range(len(lines), rows_available):
            row = self._HEADER_ROWS + 1 + i
            buf.append(_cup(row, 1) + _el())
        return "".join(buf)

    def _render_separator(self) -> str:
        t = self._theme
        row = self._rows - self._STATUS_ROWS - 1
        return (
            _cup(row, 1)
            + t.bg_separator + t.text_dim
            + "─" * self._cols
            + _RESET
        )

    def _render_status_bar(self) -> str:
        t = self._theme
        row = self._rows
        parts: list[str] = []

        for agent in self._agents:
            state = self._agent_states.get(agent, AgentState.IDLE)
            color = _state_color(state, t)

            # blink: swap filled/empty dot when running
            if state == AgentState.RUNNING and not self._blink_on:
                dot = "○"
            else:
                dot = _STATE_DOT[state]

            # spinner char next to active agent
            spinner = ""
            if state == AgentState.RUNNING:
                spinner = f" {t.text_dim}{SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]}{_RESET}"

            parts.append(
                f" {color}{dot}{_RESET} {t.text_primary}{agent}{_RESET}{spinner}"
            )

        left = "  ".join(parts)
        right = f"  {t.text_dim}{self._workspace}  {_RESET}"
        left_vis  = _strip_ansi(left)
        right_vis = _strip_ansi(right)
        pad = max(0, self._cols - len(left_vis) - len(right_vis))

        return (
            _cup(row, 1)
            + t.bg_status + t.text_secondary
            + _el()
            + left
            + " " * pad
            + right
            + _RESET
        )

    def _append_content(self, text: str) -> None:
        """Add a line to the content ring-buffer and re-render content + status."""
        with self._lock:
            self._lines.append(text)
            if len(self._lines) > self._MAX_LINES:
                self._lines = self._lines[-self._MAX_LINES:]
            if not self._active:
                # non-alt-screen fallback: just print
                print(_strip_ansi(text))
                return
            # Re-render content area and status bar (no full redraw)
            buf = (
                _sc()
                + self._render_content_block()
                + self._render_separator()
                + self._render_status_bar()
                + _rc()
            )
            self._write(buf)

    def _set_state(self, agent: str, state: AgentState) -> None:
        self._agent_states[agent] = state
        # status bar will be updated on next animation tick or content append

    def show_error_dialog(self, title: str, message: str, options: list[tuple[str, str]], *, icon: str = "⚠") -> str:
        """Render a centered modal dialog and return the chosen option key.

        Delegates to :class:`Popup` for all rendering and input.
        """
        return Popup(self).show(title=title, icon=icon, body=message, options=options)

    # ── Animation thread ───────────────────────────────────────────────────────

    def _animate(self) -> None:
        """Background thread: blink active agent dot and spin the spinner."""
        while not self._anim_stop.is_set():
            time.sleep(0.15)
            self._spinner_idx += 1
            if self._spinner_idx % 4 == 0:
                self._blink_on = not self._blink_on

            with self._lock:
                if not self._active:
                    continue
                buf = (
                    _sc()
                    + self._render_header()
                    + self._render_status_bar()
                    + _rc()
                )
                self._write(buf)

    # ── Resize ─────────────────────────────────────────────────────────────────

    def _on_resize(self, signum: int, frame: object) -> None:
        with self._lock:
            self._refresh_size()
            self._full_render()

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _write(self, text: str) -> None:
        try:
            self._stream.write(text)
            self._stream.flush()
        except Exception as exc:
            # If the terminal write itself fails, restore state and log
            try:
                from agent_coordinator.infrastructure.diagnostic_log import get_logger
                get_logger().error("tui _write failed", exc_info=exc)
            except Exception:
                pass


# ── Simple fallback (non-TTY) ─────────────────────────────────────────────────

class SimpleProgressDisplay:
    """Plain-text fallback for pipes / CI / non-TTY environments."""

    def __init__(self, stream: TextIO = sys.stdout) -> None:
        self._stream = stream

    class _FakeThinking:
        def stop(self) -> None:  pass
        running = False

    thinking     = _FakeThinking()
    stream_delay = 0.0
    max_output_lines = 999

    def start_run(self, agents: list[str], workspace: str, max_turns: int) -> None:
        w = shutil.get_terminal_size().columns
        self._p(f"\n{'─'*w}")
        self._p(f"  AGENT COORDINATOR  workspace={workspace}  max_turns={max_turns}")
        self._p("─" * w)

    def start_agent_turn(self, agent: str, backend: str, task_id: str, status: str) -> None:
        self._p(f"\n▸ {agent.upper()}  [{backend}]  task={task_id}  status={status}")
        self._p("─" * 60)

    def update_output(self, text: str) -> None:
        self._stream.write(text)
        self._stream.flush()

    def finish_agent_turn(self, success: bool, new_status: str = "", next_agent: str = "") -> None:
        if success:
            self._p(f"✓  status={new_status}  next={next_agent}")
        else:
            self._p("✗  Turn incomplete")
        self._p("─" * 60)

    def close(self) -> None:
        pass

    def _p(self, text: str = "") -> None:
        self._stream.write(text + "\n")
        self._stream.flush()


# ── Interrupt menu ────────────────────────────────────────────────────────────

class InterruptMenu:
    """Ctrl+C menu rendered as a centered popup inside the alt-screen.

    All interaction happens without leaving alternate screen.
    Falls back to plain text when not in alt-screen mode.
    """

    _ITEMS = [
        ("c", "Continue execution"),
        ("t", "Stop after this turn"),
        ("r", "Retry current turn"),
        ("e", "Edit handoff.md"),
        ("m", "Add message to handoff"),
        ("i", "Inspect handoff.md"),
        ("─", ""),
        ("n", "/init  — initialize workspace"),
        ("s", "/import-spec  — import specification"),
        ("l", "/import-plan  — import plan"),
        ("w", "/run  — switch workspace"),
        ("x", "/reset  — clear session state"),
        ("─", ""),
        ("q", "Quit"),
    ]

    def __init__(self, display: "Screen | SimpleProgressDisplay | None" = None) -> None:
        self._display = display

    # ── Public API ────────────────────────────────────────────────────────────

    def show(self) -> str:
        """Show popup menu; return chosen action key."""
        if not isinstance(self._display, Screen) or not self._display._active:
            return self._show_plain()
        return self._show_popup()

    def get_message(self, use_editor: bool = True) -> str:
        """Collect a free-text message from the user."""
        if not isinstance(self._display, Screen) or not self._display._active:
            return self._get_message_plain(use_editor)
        return self._display.read_input("Message: ")

    # ── Popup implementation ──────────────────────────────────────────────────

    def _show_popup(self) -> str:
        items: list[tuple[str, str] | None] = []
        for key, desc in self._ITEMS:
            if key == "─":
                items.append(None)
            else:
                items.append((key, desc))
        return Popup(self._display).show(
            title="INTERRUPTED",
            items=items,
            title_color=self._display._theme.color_agent,
        )

    # ── Plain-text fallback (non-TTY / no alt-screen) ─────────────────────────

    def _show_plain(self) -> str:
        w = shutil.get_terminal_size().columns
        print()
        print("═" * w)
        print("  INTERRUPTED  (Ctrl+C)")
        print("─" * w)
        for key, desc in self._ITEMS:
            if key == "─":
                print("─" * w)
            else:
                print(f"  {key:<15} {desc}")
        print("═" * w)
        sys.stdout.flush()
        try:
            from agent_coordinator.infrastructure.enhanced_input import enhanced_choice, Colors
            valid = []
            for key, _ in self._ITEMS:
                if key != "─":
                    valid.append(key[0] if key.startswith("/") else key.lower())
            choice = enhanced_choice(Colors.prompt("Choice: "), choices=valid, default="c")
        except (EOFError, KeyboardInterrupt):
            choice = "q"
        return choice

    def _get_message_plain(self, use_editor: bool = True) -> str:
        msg = ""
        if use_editor and sys.stdin.isatty():
            from agent_coordinator.infrastructure.editor import edit_handoff_message
            print("\nOpening editor for your message...")
            try:
                msg = edit_handoff_message()
            except Exception as e:
                print(f"Editor error: {e}")
        if not msg:
            from agent_coordinator.infrastructure.enhanced_input import enhanced_multiline, Colors
            print()
            msg = enhanced_multiline(
                Colors.info("Enter message (empty line to finish):"),
                Colors.prompt("> "),
            )
        return msg


# ── Utility ───────────────────────────────────────────────────────────────────

def _classify_error(exc: BaseException) -> tuple[str, str]:
    """Return (dialog title, friendly message) for a given exception."""
    msg = str(exc)

    if "not available" in msg and ("model" in msg.lower() or "--model" in msg):
        # Extract model name if present
        m = re.search(r'"([^"]+)"', msg)
        model = m.group(1) if m else "the configured model"
        return (
            "Model Not Available",
            f'The model "{model}" is not available for this backend.\n\n'
            f"Edit agents.json to change the \"model\" field for this agent,\n"
            f"or remove it to use the backend's default.",
        )

    if "No session or task matched" in msg or "not a valid UUID" in msg:
        return (
            "Stale Session",
            "The saved session ID is no longer valid.\n\n"
            "The session has been cleared. Press [r] to retry with a new session.",
        )

    if "copilot exited" in msg or "exited 1" in msg:
        # Extract the actual error line from the backend
        lines = [l.strip() for l in msg.splitlines() if l.strip()]
        detail = lines[1] if len(lines) > 1 else lines[0] if lines else msg
        return (
            "Backend Error",
            f"{detail}\n\nCheck that the CLI backend is installed and authenticated.",
        )

    if "No valid handoff block" in msg:
        return (
            "Handoff Parse Error",
            "No valid ---HANDOFF--- block found in handoff.md.\n\n"
            "The agent may not have written the required block, or the file\n"
            "may be malformed. Edit handoff.md to fix it.",
        )

    if "Unknown agent" in msg:
        return (
            "Configuration Error",
            f"{msg}\n\nEdit agents.json to fix the agent name.",
        )

    # Generic fallback
    return (
        f"{type(exc).__name__}",
        msg if msg else "An unexpected error occurred.",
    )

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)

def _wrap_text(text: str, width: int) -> list[str]:
    """Word-wrap plain text to width, preserving existing newlines."""
    import textwrap
    result: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            result.append("")
        else:
            result.extend(textwrap.wrap(paragraph, width) or [""])
    return result


# ── Factory ───────────────────────────────────────────────────────────────────

def create_display(
    reserved_lines: int = 10,
    force_simple: bool = False,
    theme: str | None = None,
) -> "Screen | SimpleProgressDisplay":
    """Return a Screen (TTY) or SimpleProgressDisplay (non-TTY / forced)."""
    if not force_simple and sys.stdout.isatty():
        return Screen(theme=get_theme(theme))
    return SimpleProgressDisplay()


# Back-compat alias
TUIDisplay = Screen

