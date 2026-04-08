"""Interactive startup CLI for agent-coordinator.

Shown when the user runs `agent-coordinator` with no arguments.
Renders entirely inside the alt-screen TUI (header + pinned status bar).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_coordinator.infrastructure.tui import Screen

try:
    import readline as _rl

    _RL = True
except ImportError:
    _RL = False


# ── Command registry ──────────────────────────────────────────────────────────


class Command:
    def __init__(self, name: str, description: str, usage: str = "", aliases: list[str] | None = None) -> None:
        self.name = name
        self.description = description
        self.usage = usage or f"/{name}"
        self.aliases = aliases or []

    def matches(self, token: str) -> bool:
        t = token.lstrip("/").lower()
        return t == self.name or t in self.aliases


COMMANDS: list[Command] = [
    Command("init", "Initialize a new workspace", "/init [path]", aliases=["i"]),
    Command("import-spec", "Import a specification file", "/import-spec [file]", aliases=["is", "spec"]),
    Command("import-plan", "Import an implementation plan", "/import-plan [file]", aliases=["ip", "plan"]),
    Command("run", "Run the coordinator on a workspace", "/run [path]", aliases=["r", "start"]),
    Command("status", "Show workspace status", "/status [path]", aliases=["s"]),
    Command("reset", "Clear saved session state", "/reset [path]", aliases=[]),
    Command("help", "Show this command list", "/help", aliases=["h", "?"]),
    Command("quit", "Exit", "/quit", aliases=["q", "exit"]),
]


# ── StartupCLI ────────────────────────────────────────────────────────────────


class StartupCLI:
    """
    Interactive slash-command prompt rendered inside the alt-screen TUI.
    Returns an action dict to main() describing what to do next.
    """

    def __init__(self, screen: Screen | None = None) -> None:
        from agent_coordinator.infrastructure.tui import create_display

        display = screen or create_display()
        if not hasattr(display, "_append_content"):
            raise RuntimeError("StartupCLI requires a TTY-capable Screen display")
        self._screen: Screen = display  # type: ignore[assignment]
        if _RL:
            _setup_readline([c.name for c in COMMANDS])

    def run(self) -> dict[str, Any]:
        """Enter TUI, show startup menu, enter command loop. Returns an action dict."""
        self._screen.start_menu()
        try:
            self._render_menu()
            while True:
                try:
                    raw = self._screen.read_input("")
                except KeyboardInterrupt:
                    return {"action": "quit", "screen": self._screen}

                if not raw:
                    continue

                action = self._dispatch(raw.strip())
                if action is not None:
                    action["screen"] = self._screen  # pass screen so caller can reuse it
                    return action
        except Exception:
            self._screen.close()
            raise

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_menu(self) -> None:
        t = self._screen._theme
        col_w = max(len(c.usage) for c in COMMANDS) + 2

        # Title
        self._screen._append_content("")
        self._screen._append_content(
            f"  {t.color_agent}\033[1magent-coordinator\033[0m  {t.text_dim}multi-agent workflow orchestrator\033[0m"
        )
        self._screen._append_content(f"  {t.text_dim}{'─' * (self._screen._cols - 4)}\033[0m")
        self._screen._append_content("")

        for cmd in COMMANDS:
            if cmd.name == "quit":
                self._screen._append_content("")
            padding = " " * (col_w - len(cmd.usage))
            line = f"  {t.color_success}\033[1m{cmd.usage}\033[0m{padding}  {t.text_secondary}{cmd.description}\033[0m"
            self._screen._append_content(line)

        self._screen._append_content("")
        self._screen._append_content(f"  {t.text_dim}type a command and press Enter  •  Tab to complete\033[0m")
        self._screen._append_content("")

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _dispatch(self, raw: str) -> dict[str, Any] | None:
        parts = raw.split()
        token, args = parts[0], parts[1:]
        cmd = next((c for c in COMMANDS if c.matches(token)), None)
        if cmd is None:
            self._screen._append_content(
                f"  {self._screen._theme.color_warning}⚠  Unknown command: {token!r}  (type /help)\033[0m"
            )
            return None
        handler: Callable[[list[str]], dict[str, Any] | None] | None = getattr(
            self, f"_cmd_{cmd.name.replace('-', '_')}", None
        )
        if handler is None:
            self._screen._append_content(
                f"  {self._screen._theme.color_warning}⚠  Not yet implemented: {cmd.name}\033[0m"
            )
            return None
        return handler(args)

    # ── Command handlers ──────────────────────────────────────────────────────

    def _cmd_init(self, args: list[str]) -> dict | None:
        path = args[0] if args else self._ask("Workspace path", default="./workspace")
        if not path:
            return None
        return {"action": "init", "workspace": Path(path).resolve()}

    def _cmd_import_spec(self, args: list[str]) -> dict | None:
        return self._import_flow(args, "spec")

    def _cmd_import_plan(self, args: list[str]) -> dict | None:
        return self._import_flow(args, "plan")

    def _import_flow(self, args: list[str], kind: str) -> dict | None:
        file = args[0] if args else self._ask(f"{kind.capitalize()} file")
        if not file:
            return None
        if not Path(file).exists():
            self._warn(f"File not found: {file}")
            return None
        path = self._ask("Workspace path", default="./workspace")
        if not path:
            return None
        force_raw = self._ask("Overwrite existing files? [y/N]", default="n")
        return {
            "action": "import",
            "file": Path(file).resolve(),
            "workspace": Path(path).resolve(),
            "type": kind,
            "force": force_raw.lower() in ("y", "yes"),
        }

    def _cmd_run(self, args: list[str]) -> dict | None:
        path = args[0] if args else self._ask("Workspace path", default="./workspace")
        if not path:
            return None
        return {"action": "run", "workspace": Path(path).resolve()}

    def _cmd_status(self, args: list[str]) -> dict | None:
        path = args[0] if args else self._ask("Workspace path", default="./workspace")
        if not path:
            return None
        self._show_status(Path(path).resolve())
        return None

    def _cmd_reset(self, args: list[str]) -> dict | None:
        path = args[0] if args else self._ask("Workspace path", default="./workspace")
        if not path:
            return None
        return {"action": "reset", "workspace": Path(path).resolve()}

    def _cmd_help(self, _: list[str]) -> dict | None:
        self._render_menu()
        return None

    def _cmd_quit(self, _: list[str]) -> dict:
        return {"action": "quit"}

    # ── Status ────────────────────────────────────────────────────────────────

    def _show_status(self, workspace: Path) -> None:
        import json

        t = self._screen._theme
        a = self._screen._append_content

        a("")
        if not workspace.exists():
            self._warn(f"Workspace not found: {workspace}")
            return

        a(f"  {t.color_agent}\033[1mWorkspace\033[0m  {t.text_primary}{workspace}\033[0m")

        handoff = workspace / "handoff.md"
        if handoff.exists():
            text = handoff.read_text(errors="replace")
            lines = text.splitlines()
            status_l = next((line for line in reversed(lines) if line.startswith("STATUS:")), None)
            next_l = next((line for line in reversed(lines) if line.startswith("NEXT:")), None)
            row = f"  {t.text_dim}handoff.md\033[0m  {t.color_success}{status_l or 'present'}\033[0m"
            if next_l:
                row += f"  {t.text_dim}{next_l}\033[0m"
            a(row)
        else:
            a(f"  {t.text_dim}handoff.md\033[0m  {t.led_error}not found\033[0m")

        tasks = workspace / "tasks.json"
        if tasks.exists():
            try:
                data = json.loads(tasks.read_text())
                task_list = data if isinstance(data, list) else data.get("tasks", [])
                done = sum(1 for x in task_list if x.get("status") == "done")
                total = len(task_list)
                a(f"  {t.text_dim}tasks.json\033[0m  {t.text_primary}{done}/{total} done\033[0m")
            except Exception:
                a(f"  {t.text_dim}tasks.json\033[0m  {t.led_blocked}parse error\033[0m")

        state_dir = workspace / ".agent-coordinator"
        sessions = state_dir / "sessions.json"
        if sessions.exists():
            try:
                sess = json.loads(sessions.read_text())
                a(f"  {t.text_dim}sessions\033[0m   {t.text_secondary}{', '.join(sess.keys()) or 'none'}\033[0m")
            except Exception:
                pass
        a("")

    # ── Input helpers ─────────────────────────────────────────────────────────

    def _ask(self, label: str, default: str = "") -> str:
        hint = f"({default}) " if default else ""
        return self._screen.read_input(f"{label} {hint}")

    def _warn(self, text: str) -> None:
        self._screen._append_content(f"  {self._screen._theme.color_warning}⚠  {text}\033[0m")


# ── readline tab-completion ───────────────────────────────────────────────────


def _setup_readline(command_names: list[str]) -> None:
    if not _RL:
        return
    slash = [f"/{n}" for n in command_names]

    def _completer(text: str, state: int) -> str | None:
        matches = [c for c in slash if c.startswith(text)]
        return matches[state] if state < len(matches) else None

    _rl.set_completer(_completer)
    _rl.set_completer_delims(" \t")
    _rl.parse_and_bind("tab: complete")

    history = Path.home() / ".agent_coordinator_history"
    try:
        if history.exists():
            _rl.read_history_file(str(history))
        import atexit

        atexit.register(_rl.write_history_file, str(history))
    except Exception:
        pass
