#!/usr/bin/env python3
"""
coordinator.py — orchestrates multi-agent workflow sessions via handoff.md.

Backend-agnostic: works with OpenCode, Claude Code, or a human operator.
Agent configuration lives in agents.json in the workspace directory.
See README.md for full usage documentation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import sys
import time
import traceback
from pathlib import Path

from agent_coordinator.application.prompt_builder import PromptBuilder
from agent_coordinator.application.router import WorkflowRouter
from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.application.task_service import TaskService
from agent_coordinator.domain.models import HandoffStatus, TaskStatus
from agent_coordinator.domain.retry_policy import RetryPolicy
from agent_coordinator.infrastructure.diagnostic_log import get_logger, log_crash, setup as setup_log
from agent_coordinator.infrastructure.event_log import EventLog
from agent_coordinator.infrastructure.handoff_reader import HandoffReader
from agent_coordinator.infrastructure.session_store import SessionStore
from agent_coordinator.infrastructure.task_repository import JsonTaskRepository

# ── Constants ─────────────────────────────────────────────────────────────────

COORDINATOR_DIR = Path(__file__).parent.resolve()
DEFAULT_WORKSPACE = Path.cwd() / "workspace"
DEFAULT_MAX_TURNS = 30
DEFAULT_HANDOFF_RETRIES = 1
SESSION_FILE = ".coordinator_sessions.json"
EVENT_LOG_FILE = "workflow_events.jsonl"
AGENTS_FILE = "agents.json"

class _QuitSignal(Exception):
    """Internal signal used to break out of the pause loop and the outer turn loop."""

_DEFAULT_AGENTS: dict = {
    "architect":   {"prompt_file": "prompts/architect.md"},
    "developer":   {"prompt_file": "prompts/developer.md"},
    "qa_engineer": {"prompt_file": "prompts/qa_engineer.md"},
}

DEFAULT_BACKEND = "copilot"

# Mapping from HandoffStatus to the TaskStatus the task should transition to.
_HANDOFF_TO_TASK_STATUS: dict[HandoffStatus, TaskStatus] = {
    HandoffStatus.CONTINUE:         TaskStatus.IN_ENGINEERING,
    HandoffStatus.REVIEW_REQUIRED:  TaskStatus.READY_FOR_ARCHITECT_REVIEW,
    HandoffStatus.REWORK_REQUIRED:  TaskStatus.REWORK_REQUESTED,
    HandoffStatus.APPROVED:         TaskStatus.DONE,
    HandoffStatus.BLOCKED:          TaskStatus.BLOCKED,
    HandoffStatus.NEEDS_HUMAN:      TaskStatus.NEEDS_HUMAN,
}

# ── Config loading ────────────────────────────────────────────────────────────

def load_config(workspace: Path) -> dict:
    """Load and return the full agents.json content, or an empty dict.

    Search order:
      1. {workspace}/agents.json          ← project-specific config
      2. {workspace}/../agents.json       ← repo-root fallback (common during dev)
    """
    for candidate in (workspace / AGENTS_FILE, workspace.parent / AGENTS_FILE):
        if candidate.exists():
            return json.loads(candidate.read_text())
    return {}


def load_agent_config(config: dict) -> dict:
    """Extract agent definitions from pre-loaded config."""
    return config.get("agents", _DEFAULT_AGENTS) if config else dict(_DEFAULT_AGENTS)


def load_retry_policy(config: dict) -> RetryPolicy:
    """Extract retry policy from pre-loaded config."""
    if config and "retry_policy" in config:
        return RetryPolicy.from_dict(config["retry_policy"])
    return RetryPolicy()


# ── Runner factory ────────────────────────────────────────────────────────────

_RUNNER_REGISTRY: dict[str, type] = {}


def _ensure_registry() -> None:
    """Lazily populate the runner registry to avoid import-time side effects."""
    if _RUNNER_REGISTRY:
        return
    from agent_coordinator.infrastructure.opencode_runner import OpenCodeRunner
    from agent_coordinator.infrastructure.claude_runner import ClaudeCodeRunner
    from agent_coordinator.infrastructure.copilot_runner import CopilotRunner
    from agent_coordinator.infrastructure.manual_runner import ManualRunner
    _RUNNER_REGISTRY.update({
        "opencode": OpenCodeRunner,
        "claude": ClaudeCodeRunner,
        "copilot": CopilotRunner,
        "manual": ManualRunner,
    })


def create_runner(backend: str, backend_config: dict | None = None, verbose: bool = True) -> AgentRunner:
    """
    Create a runner instance for the given backend name.
    
    If backend is not in the registry, tries to find executable and creates GenericRunner.
    """
    _ensure_registry()
    cls = _RUNNER_REGISTRY.get(backend)
    if cls is not None:
        return cls(verbose=verbose)
    
    # For unknown backends, try to find the executable
    from agent_coordinator.infrastructure.generic_runner import GenericRunner
    import shutil
    
    # Try to find executable
    executable = shutil.which(backend)
    
    if executable:
        # Found executable, create config automatically
        if backend_config is None:
            backend_config = {
                "executable": executable,
                "args": ["--workspace", "{workspace}"]
            }
        if verbose:
            print(f"Found {backend} executable at: {executable}")
        return GenericRunner(backend_config, verbose=verbose)
    
    # Executable not found — prompt only in interactive sessions
    if backend_config is None:
        if not sys.stdin.isatty():
            raise ValueError(
                f"Backend '{backend}' not found in supported backends and executable not in PATH.\n\n"
                f"Supported backends: {', '.join(sorted(_RUNNER_REGISTRY.keys()))}\n\n"
                f"You can:\n"
                f"  1. Provide the full path to the backend executable\n"
                f"  2. Update agents.json to use a supported backend\n"
                f"  3. Add 'backend_config' in agents.json for this backend"
            )

        from agent_coordinator.infrastructure.enhanced_input import enhanced_input, Colors

        print()
        print(Colors.warning(f"Backend '{backend}' not found in supported backends and executable not in PATH."))
        print()
        print("Supported backends:", ", ".join(sorted(_RUNNER_REGISTRY.keys())))
        print()
        print(Colors.info("You can:"))
        print("  1. Provide the full path to the backend executable")
        print("  2. Update agents.json to use a supported backend")
        print("  3. Add 'backend_config' in agents.json for this backend")
        print()

        choice = enhanced_input(
            Colors.prompt("Enter path to backend executable (or press Enter to abort): ")
        ).strip()

        if not choice:
            raise ValueError(
                f"Backend '{backend}' not available. "
                f"Update agents.json to use one of: {', '.join(sorted(_RUNNER_REGISTRY.keys()))}"
            )

        backend_config = {
            "executable": choice,
            "args": ["--workspace", "{workspace}"]
        }

        print(Colors.success(f"Using backend at: {choice}"))
    
    return GenericRunner(backend_config, verbose=verbose)


def create_runner_for_agent(agent_cfg: dict, default_backend: str, verbose: bool) -> AgentRunner:
    """Create the appropriate runner for a specific agent config."""
    backend = agent_cfg.get("backend", default_backend)
    backend_config = agent_cfg.get("backend_config")
    return create_runner(backend, backend_config, verbose=verbose)


# ── Task status sync ─────────────────────────────────────────────────────────

def _sync_task_status(
    task_service: TaskService | None,
    task_id: str,
    handoff_status: HandoffStatus,
    verbose: bool,
    event_log: EventLog | None = None,
    turn: int = 0,
    agent: str = "",
) -> None:
    """Apply the task transition implied by a handoff status, if applicable."""
    if task_service is None:
        return
    target = _HANDOFF_TO_TASK_STATUS.get(handoff_status)
    if target is None:
        return
    task = task_service.get(task_id)
    if task is None or task.status == target:
        return
    from_status = task.status.value if task else "unknown"
    try:
        task_service.update_status(task_id, target)
        if verbose:
            print(f"  ↳ tasks.json: {task_id} → {target.value}")
    except ValueError as exc:
        msg = str(exc)
        if verbose:
            print(f"  ⚠ tasks.json transition warning: {task_id} {from_status} → {target.value}: {msg}")
        if event_log is not None:
            event_log.append_warning(
                turn=turn,
                agent=agent,
                task_id=task_id,
                error=msg,
                extra={"transition_from": from_status, "transition_to": target.value},
            )


# ── Handoff file content hash ────────────────────────────────────────────────

def _file_hash(path: Path) -> str:
    """Return a hex digest of a file's content, or empty string if missing."""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _retry_prompt(agent: str, workspace: Path) -> str:
    """Prompt sent on retry attempts after the agent failed to write a valid handoff."""
    handoff = workspace / "handoff.md"
    snippet = ""
    if handoff.exists():
        lines = handoff.read_text(errors="replace").splitlines()[:10]
        snippet = "\n".join(lines)
    return (
        f"Your previous response did NOT append a valid ---HANDOFF--- block to "
        f"{workspace}/handoff.md.\n\n"
        f"Current handoff.md (first 10 lines):\n{snippet}\n\n"
        f"Please complete your work and write the required ---HANDOFF--- block "
        f"followed by ---END--- at the end of {workspace}/handoff.md."
    )


# ── Coordinator loop ──────────────────────────────────────────────────────────

class InterruptHandler:
    """Handle keyboard interrupts gracefully."""
    def __init__(self):
        self.interrupted = False
        self.original_handler = None
        
    def __enter__(self):
        self.interrupted = False
        self.original_handler = signal.signal(signal.SIGINT, self._handler)
        return self
        
    def __exit__(self, *args):
        signal.signal(signal.SIGINT, self.original_handler)
        
    def _handler(self, signum, frame):
        self.interrupted = True


def handle_interrupt(workspace: Path, handoff_path: Path) -> str:
    """Show interrupt menu and handle user choice."""
    from agent_coordinator.infrastructure.tui import InterruptMenu
    
    menu = InterruptMenu()
    choice = menu.show()
    
    if choice == 'i':
        # Inspect handoff
        if handoff_path.exists():
            print("\nCurrent handoff.md:")
            print("─" * 60)
            print(handoff_path.read_text())
            print("─" * 60)
        input("\nPress Enter to continue...")
        return handle_interrupt(workspace, handoff_path)
    
    elif choice == 'e':
        # Edit handoff directly
        from agent_coordinator.infrastructure.editor import get_editor
        import subprocess
        
        if not handoff_path.exists():
            print("ERROR: handoff.md does not exist")
            return handle_interrupt(workspace, handoff_path)
        
        editor = get_editor()
        print(f"\nOpening {handoff_path} in {editor}...")
        try:
            subprocess.run([editor, str(handoff_path)], check=True)
            print("Handoff updated")
        except Exception as e:
            print(f"Editor error: {e}")
        
        return 'c'  # Continue after editing
    
    elif choice == 'm':
        # Add message using editor
        message = menu.get_message()
        if message:
            with open(handoff_path, 'a') as f:
                f.write(f"\n\n<!-- Human intervention: {message} -->\n")
            print("Message added to handoff.md")
        return 'c'
    
    elif choice == 'u':
        # TODO: Implement undo
        print("Undo not yet implemented")
        return handle_interrupt(workspace, handoff_path)
    
    return choice


def _show_startup_popup(display, workspace: Path) -> str:
    """Show a startup popup inside the TUI. Returns the chosen action key.

    Uses the same dialog rendering as show_error_dialog.
    """
    from agent_coordinator.infrastructure.tui import Screen

    if not isinstance(display, Screen) or not display._active:
        return "r"

    handoff_path = workspace / "handoff.md"
    status_line = ""
    if handoff_path.exists():
        text = handoff_path.read_text(errors="replace")
        lines = text.splitlines()
        status_l = next((l for l in reversed(lines) if l.startswith("STATUS:")), None)
        next_l = next((l for l in reversed(lines) if l.startswith("NEXT:")), None)
        parts = []
        if status_l:
            parts.append(status_l.split(":", 1)[1].strip())
        if next_l:
            parts.append("next → " + next_l.split(":", 1)[1].strip())
        if parts:
            status_line = "  ".join(parts)
    else:
        status_line = "no handoff.md — will be created"

    summary = f"Workspace: {workspace.name}\n{status_line}" if status_line else f"Workspace: {workspace.name}"

    options = [
        ("r", "Run / continue"),
        ("i", "Inspect handoff.md"),
        ("e", "Edit handoff.md"),
        ("s", "Reset sessions"),
        ("q", "Quit"),
    ]

    choice = display.show_error_dialog("AGENT COORDINATOR", summary, options, icon="▶")

    if choice == "i":
        if handoff_path.exists():
            content = handoff_path.read_text(errors="replace")
            last_block_start = content.rfind("---HANDOFF---")
            if last_block_start >= 0:
                block = content[last_block_start:]
                for line in block.splitlines()[:20]:
                    display._append_content(f"  {display._theme.text_secondary}{line}\033[0m")
            else:
                display._append_content(f"  {display._theme.text_dim}(no handoff block found)\033[0m")
        else:
            display._append_content(f"  {display._theme.text_dim}handoff.md does not exist yet\033[0m")
        display._append_content("")
        return _show_startup_popup(display, workspace)

    if choice == "e":
        if hasattr(display, "with_editor"):
            display.with_editor(handoff_path)
        return _show_startup_popup(display, workspace)

    if choice == "s":
        from agent_coordinator.infrastructure.session_store import SessionStore
        store = SessionStore(workspace / SESSION_FILE)
        store.clear()
        display._append_content(
            f"  {display._theme.color_success}✓  Sessions cleared\033[0m"
        )
        display._append_content("")
        return _show_startup_popup(display, workspace)

    return choice

    return choice


def run_coordinator(workspace: Path, max_turns: int, reset: bool, verbose: bool, output_lines: int = 10, streaming: bool = True, display=None, auto: bool = False) -> None:
    log = setup_log(workspace)
    logger = get_logger()
    logger.info("run_coordinator start", extra={"ctx": {
        "workspace": str(workspace), "max_turns": max_turns,
        "verbose": verbose, "streaming": streaming,
    }})

    config = load_config(workspace)
    agents = load_agent_config(config)
    retry_policy = load_retry_policy(config)
    default_backend = config.get("default_backend", DEFAULT_BACKEND)

    handoff_path = workspace / "handoff.md"
    handoff_reader = HandoffReader(handoff_path)
    session_store = SessionStore(workspace / SESSION_FILE)
    event_log = EventLog(workspace / EVENT_LOG_FILE)
    router = WorkflowRouter()
    builder = PromptBuilder(coordinator_dir=COORDINATOR_DIR)

    from agent_coordinator.infrastructure.tui import create_display, InterruptMenu
    if display is None:
        display = create_display(theme=config.get("theme"))
    else:
        # Reuse the screen that was already open (e.g. from startup menu).
        # Re-apply theme if specified, but don't create a new screen.
        from agent_coordinator.infrastructure.tui import get_theme
        theme_name = config.get("theme")
        if theme_name:
            display._theme = get_theme(theme_name)
    display.max_output_lines = output_lines
    if not streaming:
        display.stream_delay = 0

    interrupt_menu = InterruptMenu(display)

    runner_cache: dict[str, AgentRunner] = {}

    tasks_path = workspace / "tasks.json"
    task_service = (
        TaskService(JsonTaskRepository(tasks_path), retry_policy=retry_policy)
        if tasks_path.exists()
        else None
    )

    if reset:
        session_store.clear()
        logger.info("session state reset")
        print("Session state reset")

    if not handoff_path.exists():
        print(f"\nHandoff file not found: {handoff_path}")
        print("Creating initial handoff.md...")
        _create_initial_handoff(workspace)
        print()

    turn_counts: dict[str, int] = {}
    total_turns = 0

    display.start_run(
        agents=list(agents.keys()),
        workspace=str(workspace),
        max_turns=max_turns,
    )

    # ── Startup popup (unless --auto) ─────────────────────────────────────
    if not auto:
        action = _show_startup_popup(display, workspace)
        if action == "q":
            display.close()
            return

    try:
        while total_turns < max_turns:
            try:
                message = handoff_reader.read()
                if message is None:
                    logger.error("no valid handoff block found in handoff.md")
                    raise RuntimeError("No valid handoff block found — check handoff.md format")

                decision = router.route(message)
                status = message.status.value

                if decision.is_terminal:
                    logger.info("workflow terminal", extra={"ctx": {"reason": decision.stop_reason}})
                    print(f"\n{decision.stop_reason}")
                    break

                agent = decision.next_actor

                if agent == "human":
                    from agent_coordinator.infrastructure.human_prompt import prompt_human_input
                    logger.info("awaiting human input", extra={"ctx": {"task": message.task_id}})
                    action = prompt_human_input(
                        handoff_path, message.task_id, status, display=display
                    )
                    if action == 'quit':
                        logger.info("human chose quit")
                        break
                    continue

                if agent not in agents:
                    logger.error("unknown agent in handoff", extra={"ctx": {
                        "agent": agent, "known": list(agents.keys()),
                    }})
                    raise RuntimeError(f"Unknown agent '{agent}'. Known: {', '.join(agents.keys())}")

                agent_cfg = agents[agent]
                if agent not in runner_cache:
                    r = create_runner_for_agent(agent_cfg, default_backend, verbose)
                    from agent_coordinator.infrastructure.manual_runner import ManualRunner
                    if isinstance(r, ManualRunner) and hasattr(display, 'read_input'):
                        r._input_fn = display.read_input
                    runner_cache[agent] = r
                runner = runner_cache[agent]
                backend_name = agent_cfg.get("backend", default_backend)

                next_task = task_service.next_ready_task() if task_service else None
                first_turn = session_store.get(agent) is None
                prompt = builder.build(agent, workspace, handoff_reader.read_raw(), agent_cfg, next_task, first_turn)

                # ── Prompt persistence (1.2) ──────────────────────────────
                turn_num = total_turns + 1
                prompts_log_dir = workspace / "prompts_log"
                prompts_log_dir.mkdir(exist_ok=True)
                prompt_file_rel = f"prompts_log/turn-{turn_num:03d}-{agent}.md"
                (workspace / prompt_file_rel).write_text(prompt, encoding="utf-8")
                prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

                logger.info("agent turn start", extra={"ctx": {
                    "agent": agent, "backend": backend_name,
                    "task": message.task_id, "status": status,
                    "turn": total_turns + 1,
                }})
                display.start_agent_turn(agent, backend_name, message.task_id, status)

                hash_before = _file_hash(handoff_path)
                handoff_updated = False

                # ── Output capture (1.1) and timing (1.3) ────────────────
                output_buffer: list[str] = []

                def _on_output(chunk: str) -> None:
                    output_buffer.append(chunk)
                    if verbose:
                        display.update_output(chunk)

                t_start = time.monotonic()
                for attempt in range(1 + DEFAULT_HANDOFF_RETRIES):
                    try:
                        run_result = runner.run(
                            message=prompt if attempt == 0 else _retry_prompt(agent, workspace),
                            workspace=workspace,
                            session_id=session_store.get(agent),
                            model=agent_cfg.get("model"),
                            on_output=_on_output,
                        )
                    except RuntimeError as e:
                        logger.error("backend error", extra={"ctx": {
                            "agent": agent, "attempt": attempt, "error": str(e),
                        }})
                        display.finish_agent_turn(success=False)
                        choice = _show_backend_error(display, e, workspace)
                        if choice == "e":
                            # Reload agents after editing
                            config = load_config(workspace)
                            agents = load_agent_config(config)
                            runner_cache.clear()
                        if choice == "q":
                            return
                        # retry or reloaded config — break out of attempt loop and re-run the turn
                        break

                    session_store.set(agent, run_result.session_id)
                    hash_after = _file_hash(handoff_path)

                    if hash_after != hash_before:
                        handoff_updated = True
                        break

                    if attempt < DEFAULT_HANDOFF_RETRIES:
                        logger.warning("handoff not updated, retrying", extra={"ctx": {
                            "agent": agent, "attempt": attempt + 1,
                        }})
                        print(f"handoff.md not updated - retrying ({attempt + 1}/{DEFAULT_HANDOFF_RETRIES})")

                turn_counts[agent] = turn_counts.get(agent, 0) + 1
                total_turns += 1
                duration_seconds = round(time.monotonic() - t_start, 2)
                response_text = "".join(output_buffer)
                del output_buffer  # free the list early

                if not handoff_updated:
                    logger.warning("agent did not update handoff", extra={"ctx": {"agent": agent}})
                    display.finish_agent_turn(success=False)
                    print(f"\nWARNING: handoff.md not updated by {agent}")
                    break

                new_message = handoff_reader.read()
                if new_message is None:
                    logger.error("invalid handoff block after agent turn", extra={"ctx": {"agent": agent}})
                    display.finish_agent_turn(success=False)
                    print(f"\nWARNING: Invalid handoff block after {agent}'s turn")
                    break

                new_status = new_message.status.value
                new_next = new_message.next

                logger.info("agent turn done", extra={"ctx": {
                    "agent": agent, "new_status": new_status, "next": new_next,
                }})
                display.finish_agent_turn(success=True, new_status=new_status, next_agent=new_next)

                _sync_task_status(
                    task_service, new_message.task_id, new_message.status, verbose,
                    event_log=event_log, turn=total_turns, agent=agent,
                )

                event_log.append(
                    turn=total_turns,
                    agent=agent,
                    task_id=message.task_id,
                    status_before=status,
                    status_after=new_status,
                    session_id=run_result.session_id,
                    response_text=response_text[:50_000],
                    prompt_file=prompt_file_rel,
                    prompt_hash=prompt_hash,
                    duration_seconds=duration_seconds,
                )
                del response_text  # free the potentially large string

                time.sleep(1)

            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt — showing interrupt menu")
                while True:
                    choice = interrupt_menu.show()
                    if choice == 'q':
                        logger.info("user quit via interrupt menu")
                        break
                    elif choice == 'c':
                        break  # continue execution
                    elif choice == 'r':
                        break  # retry — falls through to next iteration
                    elif choice == 't':
                        # Pause after this turn — enter wait loop
                        logger.info("user paused execution")
                        display.set_paused(True)
                        display._append_content(
                            f"  {display._theme.color_warning}⏸  Execution paused — Ctrl+C to resume or quit\033[0m"
                        )
                        try:
                            while True:
                                try:
                                    time.sleep(0.5)
                                except KeyboardInterrupt:
                                    resume_choice = interrupt_menu.show()
                                    if resume_choice == 'q':
                                        display.set_paused(False)
                                        logger.info("user quit from paused state")
                                        raise _QuitSignal()
                                    elif resume_choice == 'c':
                                        break
                                    elif resume_choice == 'e':
                                        if hasattr(display, 'with_editor'):
                                            display.with_editor(workspace / "handoff.md")
                                    elif resume_choice == 'i':
                                        hp = workspace / "handoff.md"
                                        if hp.exists():
                                            for ln in hp.read_text().splitlines()[-30:]:
                                                display._append_content("  " + ln)
                                    elif resume_choice == 'm':
                                        message = interrupt_menu.get_message()
                                        if message:
                                            with open(workspace / "handoff.md", "a") as _f:
                                                _f.write(f"\n\n<!-- Human intervention: {message} -->\n")
                                    elif resume_choice in ('n', 's', 'l', 'w', 'x'):
                                        _handle_popup_command(resume_choice, workspace, display)
                                    # anything else: stay paused
                        except _QuitSignal:
                            break
                        display.set_paused(False)
                        display._append_content(
                            f"  {display._theme.color_success}▶  Execution resumed\033[0m"
                        )
                        logger.info("user resumed execution")
                        break  # resume execution
                    elif choice in ('n', 's', 'l', 'w', 'x'):
                        _handle_popup_command(choice, workspace, display)
                        # re-show menu after slash command
                    elif choice == 'm':
                        message = interrupt_menu.get_message()
                        if message:
                            with open(workspace / "handoff.md", "a") as _f:
                                _f.write(f"\n\n<!-- Human intervention: {message} -->\n")
                        # re-show menu
                    elif choice == 'e':
                        if hasattr(display, 'with_editor'):
                            display.with_editor(workspace / "handoff.md")
                        else:
                            from agent_coordinator.infrastructure.editor import get_editor
                            import subprocess as _sp
                            try:
                                _sp.run([get_editor(), str(workspace / "handoff.md")], check=True)
                            except Exception as _e:
                                display._append_content(f"  Editor error: {_e}")
                        # re-show menu
                    elif choice == 'i':
                        hp = workspace / "handoff.md"
                        if hp.exists():
                            for ln in hp.read_text().splitlines()[-30:]:
                                display._append_content("  " + ln)
                        # re-show menu
                    else:
                        break  # unknown choice — continue execution

                if choice == 'q':
                    break

        else:
            logger.info("max turns reached", extra={"ctx": {"max_turns": max_turns}})
            print(f"\nReached max turns ({max_turns})")

    except Exception as exc:
        log_crash(exc, context="coordinator loop")
        from agent_coordinator.infrastructure.diagnostic_log import log_path as _lp
        lp = _lp()
        try:
            from agent_coordinator.infrastructure.tui import _classify_error
            title, friendly = _classify_error(exc)
            if lp:
                friendly += f"\n\nLog: {lp}"
            while True:
                err_choice = display.show_error_dialog(
                    title,
                    friendly,
                    [("e", "Edit handoff.md"), ("i", "Inspect handoff.md"), ("q", "Quit")],
                )
                if err_choice == "e":
                    if hasattr(display, 'with_editor'):
                        display.with_editor(workspace / "handoff.md")
                    continue
                if err_choice == "i":
                    hp = workspace / "handoff.md"
                    if hp.exists():
                        for ln in hp.read_text().splitlines()[-30:]:
                            display._append_content("  " + ln)
                    continue
                break
        except Exception:
            pass
        sys.exit(1)
    finally:
        display.close()
        logger.info("=== session end ===", extra={"ctx": {"total_turns": total_turns}})

    _print_summary(total_turns, turn_counts)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _show_backend_error(display: object, exc: Exception, workspace: Path) -> str:
    """
    Show a dialog for a backend error. Returns user choice:
      'r' — retry, 'e' — edit agents.json + retry, 'q' — quit.
    """
    from agent_coordinator.infrastructure.tui import _classify_error
    title, friendly = _classify_error(exc)

    # Offer edit option only for config-related errors
    msg_lower = str(exc).lower()
    can_edit = any(kw in msg_lower for kw in ("model", "not available", "unknown agent", "configuration"))

    options: list[tuple[str, str]] = [("r", "Retry")]
    if can_edit:
        options.append(("e", "Edit agents.json"))
    options.append(("q", "Quit"))

    choice = display.show_error_dialog(title, friendly, options)

    if choice == "e":
        _open_in_editor(workspace / "agents.json")

    return choice


def _open_in_editor(path: Path) -> None:
    """Open a file in the user's editor."""
    import subprocess
    from agent_coordinator.infrastructure.editor import get_editor
    editor = get_editor()
    try:
        subprocess.run([editor, str(path)], check=True)
    except Exception as e:
        get_logger().warning(f"editor failed: {e}")


    """Short, targeted prompt sent when an agent fails to update handoff.md."""
    return (
        f"Your previous turn did NOT append a handoff block to `{workspace}/handoff.md`. "
        f"This is required. Please append a valid `---HANDOFF---` … `---END---` block now. "
        f"Use the file-write tool to append to `{workspace}/handoff.md`."
    )


def _print_header(workspace: Path, max_turns: int, agents: dict) -> None:
    print(f"\n{'─'*60}")
    print(f"  Coordination workspace: {workspace}")
    print(f"  Max turns:  {max_turns}")
    print(f"  Agents:     {', '.join(agents.keys())}")
    print(f"{'─'*60}\n")


def _print_summary(total_turns: int, turn_counts: dict[str, int]) -> None:
    print(f"\n{'─'*60}")
    print(f"  Total turns: {total_turns}")
    for agent, count in sorted(turn_counts.items()):
        print(f"  {agent.capitalize()} turns: {count}")
    print(f"{'─'*60}")


# ── Entry point ───────────────────────────────────────────────────────────────

def _create_initial_handoff(workspace: Path) -> None:
    """Create an initial handoff.md file with a template structure."""
    handoff_path = workspace / "handoff.md"
    template = """---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: architect
TASK_ID: task-000
TITLE: Initialize project
SUMMARY: This is the initial handoff. Define project requirements, create an implementation plan, and begin task decomposition.
ACCEPTANCE:
- Project requirements understood
- Implementation plan created
- Tasks decomposed and assigned
CONSTRAINTS:
- None yet
FILES_TO_TOUCH:
- handoff.md
CHANGED_FILES:
- None
VALIDATION:
- None
BLOCKERS:
- None
---END---
"""
    handoff_path.write_text(template)
    print(f"Created initial handoff.md in {workspace}")


def _execute_startup_action(action: dict, args: argparse.Namespace) -> None:
    """Execute an action returned by StartupCLI.run()."""
    kind      = action["action"]
    workspace = action.get("workspace", Path(DEFAULT_WORKSPACE).resolve())
    screen    = action.get("screen")   # may be None for non-TUI paths

    if kind == "init":
        workspace.mkdir(parents=True, exist_ok=True)
        _create_initial_handoff(workspace)
        if screen:
            t = screen._theme
            screen._append_content(f"  {t.color_success}✓  Workspace initialised: {workspace}\033[0m")
            screen._append_content(f"  {t.text_dim}Run /run {workspace} to start\033[0m")
        else:
            print(f"\n  Workspace initialised: {workspace}")
            print(f"  Run:  agent-coordinator --workspace {workspace}\n")

    elif kind == "import":
        from agent_coordinator.helpers.import_plan import import_document
        source = action["file"]
        if screen:
            t = screen._theme
            screen._append_content(f"  {t.text_dim}Importing: {source}\033[0m")
            screen._append_content(f"  {t.text_dim}Workspace: {workspace}\033[0m")
        else:
            print(f"\n  Importing: {source}")
            print(f"  Workspace: {workspace}\n")
        import_document(
            source_path=source,
            workspace=workspace,
            doc_type=action.get("type"),
            force=action.get("force", False),
            no_handoff=False,
            no_tasks=False,
            verbose=not bool(screen),
        )
        # After import ask if user wants to run immediately
        if screen:
            answer = screen.read_input("Run coordinator now? [Y/n] ")
        else:
            try:
                answer = input("  Run coordinator now? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
        if answer.lower() in ("", "y", "yes"):
            _run_from_workspace(workspace, args, display=screen)

    elif kind == "run":
        _run_from_workspace(workspace, args, display=screen)

    elif kind == "reset":
        from agent_coordinator.infrastructure.session_store import SessionStore
        store = SessionStore(workspace / SESSION_FILE)
        store.clear()
        if screen:
            t = screen._theme
            screen._append_content(f"  {t.color_success}✓  Session state cleared for: {workspace}\033[0m")
        else:
            print(f"\n  Session state cleared for: {workspace}\n")

    elif kind == "quit":
        if screen and screen._active:
            screen.close()


def _handle_popup_command(key: str, workspace: Path, display) -> None:
    """Handle slash-command keys from the Ctrl+C popup menu."""
    t = display._theme if hasattr(display, "_theme") else None

    def _info(msg: str) -> None:
        if t and hasattr(display, "_append_content"):
            display._append_content(f"  {t.color_success}{msg}\033[0m")
        else:
            print(f"  {msg}")

    def _warn(msg: str) -> None:
        if t and hasattr(display, "_append_content"):
            display._append_content(f"  {t.color_warning}⚠  {msg}\033[0m")
        else:
            print(f"  ⚠  {msg}", file=sys.stderr)

    if key == "n":   # /init
        path_raw = display.read_input("Workspace path: ") if hasattr(display, "read_input") else input("Workspace path: ")
        new_ws = Path(path_raw).resolve() if path_raw else workspace
        new_ws.mkdir(parents=True, exist_ok=True)
        _create_initial_handoff(new_ws)
        _info(f"Workspace initialised: {new_ws}")

    elif key == "s":  # /import-spec
        _run_import(display, "spec", workspace, _info, _warn)

    elif key == "l":  # /import-plan
        _run_import(display, "plan", workspace, _info, _warn)

    elif key == "w":  # /run (switch workspace)
        path_raw = display.read_input("Workspace path: ") if hasattr(display, "read_input") else input("Workspace path: ")
        if path_raw:
            new_ws = Path(path_raw).resolve()
            _info(f"Switching to {new_ws} — restart required (use --workspace)")
        else:
            _warn("No path entered — staying on current workspace")

    elif key == "x":  # /reset
        from agent_coordinator.infrastructure.session_store import SessionStore
        store = SessionStore(workspace / SESSION_FILE)
        store.clear()
        _info(f"Session state cleared for: {workspace}")


def _run_import(display, kind: str, workspace: Path, _info, _warn) -> None:
    read = display.read_input if hasattr(display, "read_input") else input
    file_raw = read(f"{kind.capitalize()} file: ")
    if not file_raw:
        _warn("No file entered")
        return
    src = Path(file_raw).resolve()
    if not src.exists():
        _warn(f"File not found: {src}")
        return
    ws_raw = read("Workspace path: ")
    ws = Path(ws_raw).resolve() if ws_raw else workspace
    ws.mkdir(parents=True, exist_ok=True)
    _info(f"Importing {src} → {ws} …")
    from agent_coordinator.helpers.import_plan import import_document
    import_document(
        source_path=src,
        workspace=ws,
        doc_type=kind,
        force=False,
        no_handoff=False,
        no_tasks=False,
        verbose=False,
    )
    _info("Import complete")


def _run_from_workspace(workspace: Path, args: argparse.Namespace, display=None) -> None:
    """Start the coordinator loop for the given workspace."""
    if not (workspace / "handoff.md").exists():
        workspace.mkdir(parents=True, exist_ok=True)
        _create_initial_handoff(workspace)
    try:
        run_coordinator(
            workspace=workspace,
            max_turns=args.max_turns,
            reset=False,
            verbose=not args.quiet,
            output_lines=args.output_lines,
            streaming=not args.no_streaming,
            display=display,
        )
    except SystemExit:
        raise
    except Exception as exc:
        from agent_coordinator.infrastructure.diagnostic_log import log_crash, log_path
        log_crash(exc, context="startup-run")
        from agent_coordinator.infrastructure.tui import _classify_error
        title, friendly = _classify_error(exc)
        w = 60
        print(f"\n{'═'*w}", file=sys.stderr)
        print(f"  {title}", file=sys.stderr)
        for line in friendly.splitlines():
            print(f"  {line}", file=sys.stderr)
        lp = log_path()
        if lp:
            print(f"  Log: {lp}", file=sys.stderr)
        print(f"{'═'*w}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrate multi-agent AI workflows via handoff.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agent-coordinator                                    # interactive startup menu
  agent-coordinator --import SPECIFICATION.md          # import spec
  agent-coordinator --workspace ./my-project           # run coordinator
  agent-coordinator --workspace ./my-feature --reset   # reset sessions
""",
    )

    # ── Workflow arguments ────────────────────────────────────────────────────
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE,
                        help="Directory containing handoff.md and project files (default: workspace/)")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS,
                        help="Maximum agent turns before stopping (default: 30)")
    parser.add_argument("--reset", action="store_true",
                        help="Clear saved session IDs and start fresh")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-turn output")
    parser.add_argument("--output-lines", type=int, default=10,
                        help="Lines of agent output to show in the TUI window (default: 10)")
    parser.add_argument("--no-streaming", action="store_true",
                        help="Print agent output all at once instead of streaming it")
    parser.add_argument("--auto", action="store_true",
                        help="Skip the startup menu and run immediately")

    # ── Import arguments ──────────────────────────────────────────────────────
    parser.add_argument("--import", dest="import_file", type=Path, metavar="FILE",
                        help="Import a specification or implementation plan into --workspace")
    parser.add_argument("--type", choices=["spec", "plan"], default=None,
                        help="Document type for --import (default: auto-detect)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing files when importing")
    parser.add_argument("--no-handoff", action="store_true",
                        help="Skip creating handoff.md when importing")
    parser.add_argument("--no-tasks", action="store_true",
                        help="Skip creating tasks.json when importing a plan")

    args = parser.parse_args()

    # ── Startup CLI (no explicit workspace or import given) ───────────────────
    _explicit_workspace = "--workspace" in sys.argv or "-w" in sys.argv
    _has_action = args.import_file or _explicit_workspace or args.reset

    workspace = args.workspace.resolve()

    # ── Import mode ───────────────────────────────────────────────────────────
    if args.import_file:
        from agent_coordinator.helpers.import_plan import import_document
        source = args.import_file.resolve()
        if not args.quiet:
            print(f"\nImporting: {source}")
            print(f"Workspace: {workspace}")
            print()
        import_document(
            source_path=source,
            workspace=workspace,
            doc_type=args.type,
            force=args.force,
            no_handoff=args.no_handoff,
            no_tasks=args.no_tasks,
            verbose=not args.quiet,
        )
        if not args.quiet:
            print()
            print("Done. Run the coordinator to start:")
            print(f"  agent-coordinator --workspace {workspace}")
        return

    # ── Coordinator mode ──────────────────────────────────────────────────────
    if not (workspace / "handoff.md").exists():
        workspace.mkdir(parents=True, exist_ok=True)
        _create_initial_handoff(workspace)

    try:
        run_coordinator(
            workspace=workspace,
            max_turns=args.max_turns,
            reset=args.reset,
            verbose=not args.quiet,
            output_lines=args.output_lines,
            streaming=not args.no_streaming,
            auto=args.auto,
        )
    except SystemExit:
        raise
    except Exception as exc:
        from agent_coordinator.infrastructure.diagnostic_log import log_crash, log_path
        log_crash(exc, context="main")
        lp = log_path()
        # Terminal is already restored by run_coordinator's finally block.
        # Print a clean error — no raw traceback to the user.
        from agent_coordinator.infrastructure.tui import _classify_error
        title, friendly = _classify_error(exc)
        w = 60
        print(f"\n{'═'*w}", file=sys.stderr)
        print(f"  {title}", file=sys.stderr)
        print(f"{'─'*w}", file=sys.stderr)
        for line in friendly.splitlines():
            print(f"  {line}", file=sys.stderr)
        if lp:
            print(f"{'─'*w}", file=sys.stderr)
            print(f"  Log: {lp}", file=sys.stderr)
        print(f"{'═'*w}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

