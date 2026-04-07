"""Interactive startup CLI for agent-coordinator.

Shown when the user runs `agent-coordinator` with no arguments.
Presents a command menu styled after copilot-cli's slash-command interface.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

try:
    import readline
    _RL = True
except ImportError:
    _RL = False

# ── ANSI ─────────────────────────────────────────────────────────────────────

ESC = "\033"
_R   = ESC + "[0m"
_B   = ESC + "[1m"
_DIM = ESC + "[2m"

def _fg(r: int, g: int, b: int) -> str: return ESC + f"[38;2;{r};{g};{b}m"
def _bg(r: int, g: int, b: int) -> str: return ESC + f"[48;2;{r};{g};{b}m"

# Catppuccin Frappé
C_BLUE    = _fg(140, 170, 238)   # Blue
C_GREEN   = _fg(166, 209, 137)   # Green
C_PEACH   = _fg(239, 159, 118)   # Peach
C_MAUVE   = _fg(202, 158, 230)   # Mauve
C_TEXT    = _fg(198, 208, 245)   # Text
C_SUB     = _fg(165, 173, 206)   # Subtext0
C_DIM     = _fg(115, 121, 148)   # Overlay0
C_RED     = _fg(231, 130, 132)   # Red
BG_HEADER = _bg(35,  38,  52)    # Crust


# ── Command registry ──────────────────────────────────────────────────────────

class Command:
    def __init__(
        self,
        name: str,
        description: str,
        usage: str = "",
        aliases: list[str] | None = None,
    ) -> None:
        self.name        = name
        self.description = description
        self.usage       = usage or name
        self.aliases     = aliases or []

    def matches(self, token: str) -> bool:
        t = token.lstrip("/").lower()
        return t == self.name or t in self.aliases


COMMANDS: list[Command] = [
    Command("init",         "Initialize a new workspace",
            usage="/init [path]",         aliases=["i"]),
    Command("import-spec",  "Import a specification file",
            usage="/import-spec [file]",  aliases=["is", "spec"]),
    Command("import-plan",  "Import an implementation plan",
            usage="/import-plan [file]",  aliases=["ip", "plan"]),
    Command("run",          "Run the coordinator on a workspace",
            usage="/run [path]",          aliases=["r", "start"]),
    Command("status",       "Show workspace status",
            usage="/status [path]",       aliases=["s"]),
    Command("reset",        "Clear saved session state",
            usage="/reset [path]",        aliases=[]),
    Command("help",         "Show this command list",
            usage="/help",                aliases=["h", "?"]),
    Command("quit",         "Exit",
            usage="/quit",                aliases=["q", "exit"]),
]

_COMMAND_NAMES = [f"/{c.name}" for c in COMMANDS]


# ── StartupCLI ────────────────────────────────────────────────────────────────

class StartupCLI:
    """
    Interactive slash-command prompt shown at startup.

    Returns an action dict to main() describing what to do next.
    """

    def __init__(self) -> None:
        self._history: list[str] = []
        if _RL:
            _setup_readline([c.name for c in COMMANDS])

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self) -> dict:
        """Show the welcome screen, then enter the command loop. Returns an action dict."""
        self._print_header()
        self._print_commands()

        while True:
            try:
                raw = self._prompt()
            except (EOFError, KeyboardInterrupt):
                self._println()
                return {"action": "quit"}

            if not raw.strip():
                continue

            self._history.append(raw)
            action = self._dispatch(raw.strip())
            if action is not None:
                return action

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _print_header(self) -> None:
        import shutil
        w = shutil.get_terminal_size().columns
        self._println()
        self._println(BG_HEADER + C_BLUE + _B + "  agent-coordinator" + _R +
                      C_DIM + "  multi-agent workflow orchestrator" + _R)
        self._println(C_DIM + "─" * min(w, 72) + _R)
        self._println()

    def _print_commands(self) -> None:
        col_w = max(len(c.usage) for c in COMMANDS) + 2
        for cmd in COMMANDS:
            if cmd.name == "quit":
                self._println()   # visual gap before quit
            # pad based on visible (no-ANSI) length
            visible_usage = cmd.usage
            padding = " " * (col_w - len(visible_usage))
            styled_usage = C_GREEN + _B + visible_usage + _R + padding
            self._println(f"  {styled_usage}  {C_SUB}{cmd.description}{_R}")
        self._println()

    # ── Prompt ────────────────────────────────────────────────────────────────

    def _prompt(self) -> str:
        prompt_str = C_MAUVE + _B + "❯ " + _R + C_TEXT
        # Reset color after input on some terminals
        suffix = _R
        try:
            value = input(prompt_str)
            sys.stdout.write(suffix)
            sys.stdout.flush()
            return value
        except UnicodeDecodeError:
            return ""

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _dispatch(self, raw: str) -> dict | None:
        parts = raw.split()
        token = parts[0]
        args  = parts[1:]

        cmd = next((c for c in COMMANDS if c.matches(token)), None)
        if cmd is None:
            self._warn(f"Unknown command: {token!r}  (type /help for a list)")
            return None

        handler = getattr(self, f"_cmd_{cmd.name.replace('-', '_')}", None)
        if handler is None:
            self._warn(f"Command not yet implemented: {cmd.name}")
            return None

        return handler(args)

    # ── Command handlers ──────────────────────────────────────────────────────

    def _cmd_init(self, args: list[str]) -> dict | None:
        path = self._ask_path(args, "Workspace path", default="./workspace")
        if path is None:
            return None
        return {"action": "init", "workspace": Path(path).resolve()}

    def _cmd_import_spec(self, args: list[str]) -> dict | None:
        file = self._ask_file(args, "Specification file")
        if file is None:
            return None
        path = self._ask_path([], "Workspace path", default="./workspace")
        if path is None:
            return None
        force = self._ask_bool("Overwrite existing files?", default=False)
        return {
            "action": "import",
            "file": Path(file).resolve(),
            "workspace": Path(path).resolve(),
            "type": "spec",
            "force": force,
        }

    def _cmd_import_plan(self, args: list[str]) -> dict | None:
        file = self._ask_file(args, "Plan file")
        if file is None:
            return None
        path = self._ask_path([], "Workspace path", default="./workspace")
        if path is None:
            return None
        force = self._ask_bool("Overwrite existing files?", default=False)
        return {
            "action": "import",
            "file": Path(file).resolve(),
            "workspace": Path(path).resolve(),
            "type": "plan",
            "force": force,
        }

    def _cmd_run(self, args: list[str]) -> dict | None:
        path = self._ask_path(args, "Workspace path", default="./workspace")
        if path is None:
            return None
        return {"action": "run", "workspace": Path(path).resolve()}

    def _cmd_status(self, args: list[str]) -> dict | None:
        path = self._ask_path(args, "Workspace path", default="./workspace")
        if path is None:
            return None
        self._show_status(Path(path).resolve())
        return None   # stay in the loop

    def _cmd_reset(self, args: list[str]) -> dict | None:
        path = self._ask_path(args, "Workspace path", default="./workspace")
        if path is None:
            return None
        return {"action": "reset", "workspace": Path(path).resolve()}

    def _cmd_help(self, args: list[str]) -> dict | None:
        self._println()
        self._print_commands()
        return None

    def _cmd_quit(self, args: list[str]) -> dict:
        return {"action": "quit"}

    # ── Status display ────────────────────────────────────────────────────────

    def _show_status(self, workspace: Path) -> None:
        import json
        self._println()
        if not workspace.exists():
            self._warn(f"Workspace not found: {workspace}")
            return

        self._println(f"  {C_BLUE}{_B}Workspace{_R}  {C_TEXT}{workspace}{_R}")

        handoff = workspace / "handoff.md"
        if handoff.exists():
            # Extract last STATUS line
            text = handoff.read_text(errors="replace")
            lines = text.splitlines()
            status_line = next((l for l in reversed(lines) if l.startswith("STATUS:")), None)
            next_line   = next((l for l in reversed(lines) if l.startswith("NEXT:")), None)
            self._println(f"  {C_DIM}handoff.md{_R}  "
                          f"{C_GREEN}{status_line or 'present'}{_R}"
                          + (f"  {C_SUB}{next_line}{_R}" if next_line else ""))
        else:
            self._println(f"  {C_DIM}handoff.md{_R}  {C_RED}not found{_R}")

        tasks = workspace / "tasks.json"
        if tasks.exists():
            try:
                data = json.loads(tasks.read_text())
                task_list = data if isinstance(data, list) else data.get("tasks", [])
                done  = sum(1 for t in task_list if t.get("status") == "done")
                total = len(task_list)
                self._println(f"  {C_DIM}tasks.json{_R}  {C_TEXT}{done}/{total} done{_R}")
            except Exception:
                self._println(f"  {C_DIM}tasks.json{_R}  {C_PEACH}parse error{_R}")

        agents_f = workspace / "agents.json"
        if not agents_f.exists():
            agents_f = Path("agents.json")
        if agents_f.exists():
            self._println(f"  {C_DIM}agents.json{_R}  {C_GREEN}found{_R}")

        sessions = workspace / ".coordinator_sessions.json"
        if sessions.exists():
            import json as _j
            try:
                sess = _j.loads(sessions.read_text())
                self._println(f"  {C_DIM}sessions{_R}   {C_TEXT}{', '.join(sess.keys()) or 'none'}{_R}")
            except Exception:
                pass
        self._println()

    # ── Input helpers ─────────────────────────────────────────────────────────

    def _ask_path(self, args: list[str], label: str, default: str) -> str | None:
        if args:
            return args[0]
        return self._ask(f"  {C_DIM}{label}{_R}", default=default)

    def _ask_file(self, args: list[str], label: str) -> str | None:
        if args:
            p = args[0]
        else:
            p = self._ask(f"  {C_DIM}{label}{_R}", default="")
        if not p:
            self._warn("No file specified.")
            return None
        if not Path(p).exists():
            self._warn(f"File not found: {p}")
            return None
        return p

    def _ask_bool(self, question: str, default: bool = False) -> bool:
        hint = "Y/n" if default else "y/N"
        answer = self._ask(f"  {C_DIM}{question}{_R} [{hint}]", default="")
        if not answer:
            return default
        return answer.strip().lower() in ("y", "yes", "1", "true")

    def _ask(self, label: str, default: str = "") -> str | None:
        hint = f" {C_DIM}({default}){_R}" if default else ""
        prompt = f"{label}{hint}{C_MAUVE} › {_R}{C_TEXT}"
        suffix = _R
        try:
            value = input(prompt)
            sys.stdout.write(suffix)
            sys.stdout.flush()
            return value.strip() or default
        except (EOFError, KeyboardInterrupt):
            self._println()
            return None

    # ── Output ────────────────────────────────────────────────────────────────

    def _println(self, text: str = "") -> None:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def _warn(self, text: str) -> None:
        self._println(f"\n  {C_PEACH}⚠  {text}{_R}\n")


# ── readline setup ────────────────────────────────────────────────────────────

def _setup_readline(command_names: list[str]) -> None:
    if not _RL:
        return

    slash_names = [f"/{n}" for n in command_names]

    def _completer(text: str, state: int) -> str | None:
        matches = [c for c in slash_names if c.startswith(text)]
        return matches[state] if state < len(matches) else None

    readline.set_completer(_completer)
    readline.set_completer_delims(" \t")
    readline.parse_and_bind("tab: complete")

    # History file
    history_path = Path.home() / ".agent_coordinator_history"
    try:
        if history_path.exists():
            readline.read_history_file(str(history_path))
        import atexit
        atexit.register(readline.write_history_file, str(history_path))
    except Exception:
        pass
