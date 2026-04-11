#!/usr/bin/env python3
"""
coordinator.py — orchestrates multi-agent workflow sessions via handoff.md.

Backend-agnostic: works with OpenCode, Claude Code, or a human operator.
Agent configuration lives in agents.json in the workspace directory.
See README.md for full usage documentation.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_coordinator.infrastructure.tui import Screen

from agent_coordinator.application.prompt_builder import PromptBuilder
from agent_coordinator.application.task_classifier import (
    default_agent_for_mode,
    expected_outputs_for_mode,
    infer_task_mode,
    task_has_delivery_artifacts,
)
from agent_coordinator.application.router import WorkflowRouter
from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.application.task_service import TaskService
from agent_coordinator.domain.models import HandoffMessage, HandoffStatus, TaskMode, TaskStatus, WorkflowState
from agent_coordinator.domain.retry_policy import RetryPolicy
from agent_coordinator.infrastructure.diagnostic_log import get_logger, log_crash
from agent_coordinator.infrastructure.diagnostic_log import setup as setup_log
from agent_coordinator.infrastructure.event_log import EventLog
from agent_coordinator.infrastructure.handoff_reader import HandoffReader
from agent_coordinator.infrastructure.session_store import SessionStore
from agent_coordinator.infrastructure.task_repository import JsonTaskRepository
from agent_coordinator.infrastructure.workflow_state_repository import WorkflowStateRepository
from agent_coordinator.handoff_parser import extract_latest

# ── Constants ─────────────────────────────────────────────────────────────────

COORDINATOR_DIR = Path(__file__).parent.resolve()
DEFAULT_WORKSPACE = Path.cwd()
DEFAULT_MAX_TURNS = 0  # 0 means unlimited
DEFAULT_HANDOFF_RETRIES = 1
STATE_DIR = ".agent-coordinator"
SESSION_FILE = "sessions.json"
EVENT_LOG_FILE = "events.jsonl"
WORKFLOW_STATE_FILE = "workflow_state.json"
AGENTS_FILE = "agents.json"


def _state_dir(workspace: Path) -> Path:
    """Return the coordinator state directory, creating it if needed."""
    d = workspace / STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


class _QuitSignalError(Exception):
    """Internal signal used to break out of the pause loop and the outer turn loop."""


_DEFAULT_AGENTS: dict = {
    "architect": {"prompt_file": "prompts/architect.md", "supportsStatelessMode": False},
    "developer": {"prompt_file": "prompts/developer.md", "supportsStatelessMode": True},
    "qa_engineer": {"prompt_file": "prompts/qa_engineer.md", "supportsStatelessMode": True},
}

DEFAULT_BACKEND = "copilot"

# Mapping from HandoffStatus to the TaskStatus the task should transition to.
_HANDOFF_TO_TASK_STATUS: dict[HandoffStatus, TaskStatus] = {
    HandoffStatus.CONTINUE: TaskStatus.IN_ENGINEERING,
    HandoffStatus.REVIEW_REQUIRED: TaskStatus.READY_FOR_ARCHITECT_REVIEW,
    HandoffStatus.REWORK_REQUIRED: TaskStatus.REWORK_REQUESTED,
    HandoffStatus.APPROVED: TaskStatus.DONE,
    HandoffStatus.BLOCKED: TaskStatus.BLOCKED,
    HandoffStatus.NEEDS_HUMAN: TaskStatus.NEEDS_HUMAN,
}

# ── Config loading ────────────────────────────────────────────────────────────


def load_config(workspace: Path) -> dict[str, Any]:
    """Load and return the full agents.json content, or an empty dict.

    Search order:
      1. {workspace}/agents.json          ← project-specific config
      2. {workspace}/../agents.json       ← repo-root fallback (common during dev)
    """
    for candidate in (workspace / AGENTS_FILE, workspace.parent / AGENTS_FILE):
        if candidate.exists():
            data: dict[str, Any] = json.loads(candidate.read_text())
            return data
    return {}


def load_agent_config(config: dict) -> dict:
    """Extract agent definitions from pre-loaded config."""
    return config.get("agents", _DEFAULT_AGENTS) if config else dict(_DEFAULT_AGENTS)


def load_retry_policy(config: dict) -> RetryPolicy:
    """Extract retry policy from pre-loaded config."""
    if config and "retry_policy" in config:
        return RetryPolicy.from_dict(config["retry_policy"])
    return RetryPolicy()


def agent_supports_stateless_mode(agent: str, agent_cfg: dict[str, Any]) -> bool:
    """Return whether the agent should honor the global --stateless flag."""
    if "supportsStatelessMode" in agent_cfg:
        return bool(agent_cfg["supportsStatelessMode"])
    return agent != "architect"


# ── Runner factory ────────────────────────────────────────────────────────────

# All concrete runners accept (verbose: bool) in __init__
_RunnerFactory = Callable[..., AgentRunner]
_RUNNER_REGISTRY: dict[str, _RunnerFactory] = {}


def _ensure_registry() -> None:
    """Lazily populate the runner registry to avoid import-time side effects."""
    if _RUNNER_REGISTRY:
        return
    from agent_coordinator.infrastructure.claude_runner import ClaudeCodeRunner
    from agent_coordinator.infrastructure.copilot_runner import CopilotRunner
    from agent_coordinator.infrastructure.manual_runner import ManualRunner
    from agent_coordinator.infrastructure.opencode_runner import OpenCodeRunner

    _RUNNER_REGISTRY.update(
        {
            "opencode": OpenCodeRunner,
            "claude": ClaudeCodeRunner,
            "copilot": CopilotRunner,
            "manual": ManualRunner,
        }
    )


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
    import shutil

    from agent_coordinator.infrastructure.generic_runner import GenericRunner

    # Try to find executable
    executable = shutil.which(backend)

    if executable:
        # Found executable, create config automatically
        if backend_config is None:
            backend_config = {"executable": executable, "args": ["--workspace", "{workspace}"]}
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

        from agent_coordinator.infrastructure.enhanced_input import Colors, enhanced_input

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

        choice = enhanced_input(Colors.prompt("Enter path to backend executable (or press Enter to abort): ")).strip()

        if not choice:
            raise ValueError(
                f"Backend '{backend}' not available. "
                f"Update agents.json to use one of: {', '.join(sorted(_RUNNER_REGISTRY.keys()))}"
            )

        backend_config = {"executable": choice, "args": ["--workspace", "{workspace}"]}

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


def _retry_prompt(_agent: str, workspace: Path) -> str:
    """Prompt sent on retry attempts after the agent failed to return a valid handoff."""
    handoff = workspace / "handoff.md"
    snippet = ""
    if handoff.exists():
        lines = handoff.read_text(errors="replace").splitlines()[:10]
        snippet = "\n".join(lines)
    return (
        f"Your previous response did NOT append/include a valid ---HANDOFF--- block.\n\n"
        f"Current derived handoff log (first 10 lines of {workspace}/handoff.md):\n{snippet}\n\n"
        f"Please complete your work and return the required ---HANDOFF--- block "
        f"followed by ---END--- in your response."
    )


def _bootstrap_tasks(workspace: Path) -> Path:
    """Create a minimal tasks.json when no structured task state exists yet."""
    tasks_path = workspace / "tasks.json"
    if tasks_path.exists():
        return tasks_path
    from datetime import datetime, timezone

    workspace.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    spec_exists = any((workspace / name).exists() for name in ("SPECIFICATION.md", "spec.md", "PRD.md", "requirements.md"))
    task = {
        "id": "task-000",
        "title": "Create implementation plan" if spec_exists else "Initialize project",
        "status": "planned",
        "mode": TaskMode.PLANNING.value,
        "description": (
            "Read the project requirements, define scope, and create executable implementation tasks."
            if spec_exists
            else "Clarify the goal, define scope, and create the first executable tasks."
        ),
        "priority": 0,
        "owner": "",
        "acceptance_criteria": [
            "Scope is clear enough to begin building",
            "Dependencies are identified",
            "At least one executable implementation task exists",
        ],
        "constraints": [],
        "files_to_touch": ["tasks.json", "plan.md"],
        "changed_files": [],
        "artifacts": [],
        "validation_results": [],
        "validation_status": "pending",
        "unresolved_issues": [],
        "follow_up_tasks": [],
        "rework_count": 0,
        "depends_on": [],
        "created_at": now,
        "updated_at": now,
    }
    tasks_path.write_text(json.dumps({"version": 1, "tasks": [task]}, indent=2), encoding="utf-8")
    return tasks_path


def _initial_workflow_state(
    repo: WorkflowStateRepository,
    handoff_reader: HandoffReader,
    task_service: TaskService | None,
) -> WorkflowState:
    """Load workflow state, seeding it from tasks and legacy handoff when needed."""
    state = repo.load()
    if state.pending_task_id and state.pending_actor:
        return state
    if task_service is not None:
        task = task_service.next_ready_task()
        if task is not None:
            state.pending_task_id = task.id
            state.pending_actor = task_service.default_agent_for_task(task)
            state.pending_status = task.status.value
    message = handoff_reader.read()
    if message is not None:
        state.pending_task_id = message.task_id or state.pending_task_id
        if message.status in {HandoffStatus.PLAN_COMPLETE, HandoffStatus.DONE, HandoffStatus.APPROVED, HandoffStatus.IMPLEMENTATION_COMPLETE}:
            state.pending_actor = ""
        elif message.next not in ("none", "human"):
            state.pending_actor = message.next
        state.pending_status = message.status.value
        state.pending_summary = message.summary
    repo.save(state)
    return state


def _normalize_list(items: list[str]) -> list[str]:
    cleaned = []
    seen = set()
    for item in items:
        value = item.strip()
        if not value or value.lower() in {"n/a", "none"}:
            continue
        if value not in seen:
            cleaned.append(value)
            seen.add(value)
    return cleaned


def _plan_files(workspace: Path) -> list[Path]:
    """Return plan documents available in the workspace."""
    root_files = [workspace / name for name in ("plan.md", "PLAN.md", "IMPLEMENTATION_PLAN.md", "implementation_plan.md")]
    found = [path for path in root_files if path.exists()]
    for dirname in ("plans", "plan", "implementation_plans"):
        directory = workspace / dirname
        if directory.is_dir():
            found.extend(sorted(path for path in directory.rglob("*.md") if path.is_file()))
    unique: list[Path] = []
    seen = set()
    for path in found:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def _start_task_generation_from_plan(workspace: Path) -> bool:
    """Seed missing tasks from plan docs and route the next turn to planning."""
    plan_files = _plan_files(workspace)
    if not plan_files:
        return False

    from datetime import datetime, timezone

    from agent_coordinator.helpers.import_plan import extract_tasks_from_plan

    tasks_path = _bootstrap_tasks(workspace)
    task_service = TaskService(JsonTaskRepository(tasks_path))
    existing_ids = {task.id for task in task_service.all()}
    now = datetime.now(timezone.utc).isoformat()
    inserted = False
    for index, plan_file in enumerate(plan_files, start=1):
        extracted = extract_tasks_from_plan(plan_file.read_text(encoding="utf-8"))
        for task_data in extracted:
            if task_data["id"] in existing_ids:
                continue
            task_service.ensure_task(
                task_data["id"],
                task_data["title"],
                mode=TaskMode(task_data.get("mode", infer_task_mode(task_data["title"], task_data.get("description", "")).value)),
                description=task_data.get("description", ""),
            )
            task = task_service.get(task_data["id"])
            assert task is not None
            task.priority = int(task_data.get("priority", 100 + index))
            task.acceptance_criteria = task_data.get("acceptance_criteria", [])
            task.constraints = task_data.get("constraints", [])
            task.files_to_touch = task_data.get("files_to_touch", [])
            task.depends_on = task_data.get("depends_on", [])
            task.owner = task_data.get("owner", "")
            task.created_at = task_data.get("created_at", now)
            task.updated_at = task_data.get("updated_at", now)
            task_service.save(task)
            existing_ids.add(task.id)
            inserted = True

    planning_task = task_service.ensure_task(
        "task-plan-refresh",
        "Add new tasks from plan",
        mode=TaskMode.PLANNING,
        description="Review the plan documents, add any missing executable tasks to tasks.json, and stop once implementation can proceed.",
    )
    planning_task.status = TaskStatus.PLANNED
    planning_task.priority = -10
    planning_task.owner = "architect"
    planning_task.files_to_touch = _normalize_list(
        planning_task.files_to_touch + [str(path.relative_to(workspace)) for path in plan_files] + ["tasks.json"]
    )
    planning_task.acceptance_criteria = [
        "Any missing executable tasks from the plan are added to tasks.json",
        "Dependencies for new tasks are identified",
        "Planning stops once the next implementation task is concrete and testable",
    ]
    task_service.save(planning_task)

    workflow_repo = WorkflowStateRepository(_state_dir(workspace) / WORKFLOW_STATE_FILE)
    workflow_state = workflow_repo.load()
    workflow_state.pending_task_id = planning_task.id
    workflow_state.pending_actor = "architect"
    workflow_state.pending_status = planning_task.status.value
    workflow_state.pending_summary = (
        "Startup choice: add new tasks from the plan."
        + (" Missing plan tasks were seeded into structured state." if inserted else " Review plan docs for additional executable tasks.")
    )
    workflow_repo.save(workflow_state)
    return True


def _handoff_block_from_message(message: HandoffMessage) -> str:
    def _section(name: str, values: list[str]) -> str:
        vals = _normalize_list(values)
        if not vals:
            return f"{name}:\n- none"
        return f"{name}:\n" + "\n".join(f"- {value}" for value in vals)

    parts = [
        "---HANDOFF---",
        f"ROLE: {message.role}",
        f"STATUS: {message.status.value}",
        f"NEXT: {message.next}",
        f"TASK_ID: {message.task_id}",
        f"TITLE: {message.title}",
        f"SUMMARY: {message.summary}",
        _section("ACCEPTANCE", message.acceptance),
        _section("CONSTRAINTS", message.constraints),
        _section("FILES_TO_TOUCH", message.files_to_touch),
        _section("CHANGED_FILES", message.changed_files),
        _section("VALIDATION", message.validation),
        _section("BLOCKERS", message.blockers),
        "---END---",
    ]
    return "\n".join(parts) + "\n"


def _append_handoff_log(handoff_path: Path, message: HandoffMessage) -> None:
    """Append a normalized handoff entry at EOF."""
    from datetime import datetime, timezone

    prefix = f"## {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} — {message.role}\n\n"
    existing = handoff_path.read_text(encoding="utf-8") if handoff_path.exists() else ""
    separator = "" if not existing else ("\n" if existing.endswith("\n") else "\n\n")
    handoff_path.write_text(existing + separator + prefix + _handoff_block_from_message(message), encoding="utf-8")


def _extract_agent_message(response_text: str, handoff_reader: HandoffReader) -> HandoffMessage | None:
    """Parse a structured handoff block from agent output, with file fallback."""
    message, _errors = extract_latest(response_text)
    if message is not None:
        return message
    return handoff_reader.read()


def _transition_key(task_id: str, from_status: str, to_status: str, assigned_agent: str) -> str:
    return f"{task_id}|{from_status}|{to_status}|{assigned_agent}"


def _desired_task_status(message: HandoffMessage) -> TaskStatus | None:
    if message.status == HandoffStatus.CONTINUE:
        return TaskStatus.READY_FOR_ENGINEERING
    if message.status == HandoffStatus.REVIEW_REQUIRED:
        return TaskStatus.READY_FOR_ARCHITECT_REVIEW
    if message.status == HandoffStatus.REWORK_REQUIRED:
        return TaskStatus.REWORK_REQUESTED
    if message.status in {HandoffStatus.APPROVED, HandoffStatus.DONE, HandoffStatus.PLAN_COMPLETE, HandoffStatus.IMPLEMENTATION_COMPLETE}:
        return TaskStatus.DONE
    if message.status == HandoffStatus.BLOCKED:
        return TaskStatus.BLOCKED
    if message.status == HandoffStatus.NEEDS_HUMAN:
        return TaskStatus.NEEDS_HUMAN
    return None


def _next_mode(current_mode: TaskMode, message: HandoffMessage) -> TaskMode:
    if message.next == "qa_engineer":
        return TaskMode.VERIFICATION
    if message.next == "architect" and message.status == HandoffStatus.REVIEW_REQUIRED:
        return TaskMode.REVIEW
    if message.next == "developer" and message.status == HandoffStatus.REWORK_REQUIRED:
        return TaskMode.REPAIR
    return current_mode


def _update_task_from_message(
    ctx: _CoordinatorContext,
    active_task_id: str,
    agent: str,
    message: HandoffMessage,
) -> tuple[str, str, bool]:
    """Apply an agent result to structured task state."""
    if ctx.task_service is None:
        return "", "", False
    active_task = ctx.task_service.ensure_task(active_task_id, message.title, mode=infer_task_mode(message.title, message.summary))
    task = ctx.task_service.ensure_task(
        message.task_id or active_task_id,
        message.title,
        mode=infer_task_mode(message.title, message.summary, message.acceptance, message.files_to_touch),
        description=message.summary,
    )
    progress = False
    if active_task.id != task.id and active_task.mode in (TaskMode.PLANNING, TaskMode.DISCOVERY):
        active_task.status = TaskStatus.DONE
        ctx.task_service.save(active_task)
        progress = True

    before_status = task.status.value
    old_changed = list(task.changed_files)
    old_validation = list(task.validation_results)
    task.title = message.title or task.title
    if message.summary:
        task.description = message.summary
    if message.acceptance:
        task.acceptance_criteria = _normalize_list(message.acceptance)
    if message.constraints:
        task.constraints = _normalize_list(message.constraints)
    if message.files_to_touch:
        task.files_to_touch = _normalize_list(message.files_to_touch)
    task.changed_files = _normalize_list(task.changed_files + message.changed_files)
    task.artifacts = _normalize_list(task.artifacts + message.changed_files)
    task.validation_results = _normalize_list(task.validation_results + message.validation)
    task.validation_status = "passed" if task.validation_results and not message.blockers else task.validation_status
    task.unresolved_issues = _normalize_list(task.unresolved_issues + message.blockers)
    task.owner = message.next
    task.mode = _next_mode(task.mode, message)

    desired = _desired_task_status(message)
    if task.mode in (TaskMode.IMPLEMENTATION, TaskMode.REPAIR) and message.status == HandoffStatus.REVIEW_REQUIRED:
        if not task_has_delivery_artifacts(task):
            desired = TaskStatus.REWORK_REQUESTED
            task.unresolved_issues = _normalize_list(task.unresolved_issues + ["No delivery artifacts were produced"])
    if desired is not None:
        task.status = desired
    ctx.task_service.save(task)

    if before_status != task.status.value:
        progress = True
    if task.changed_files != old_changed or task.validation_results != old_validation:
        progress = True
    return task.id, before_status, progress


def _recover_from_coordination_loop(ctx: _CoordinatorContext) -> None:
    """Select the next ready executable task when meta-work stalls progress."""
    if ctx.task_service is None:
        return
    ready = ctx.task_service.ready_queue()
    if not ready:
        return
    for task in ready:
        if task.mode in (TaskMode.IMPLEMENTATION, TaskMode.REPAIR, TaskMode.VERIFICATION):
            ctx.workflow_state.pending_task_id = task.id
            ctx.workflow_state.pending_actor = ctx.task_service.default_agent_for_task(task)
            ctx.workflow_state.pending_status = task.status.value
            ctx.workflow_state.pending_summary = "Loop recovery selected the next executable task."
            ctx.workflow_state.no_progress_turns = 0
            ctx.workflow_state.recovery_count += 1
            ctx.workflow_state_repo.save(ctx.workflow_state)
            return


def _select_pending_turn(ctx: _CoordinatorContext) -> tuple[str, Any, str] | None:
    """Choose the next actor/task from structured state."""
    if ctx.task_service is None:
        return None
    state = ctx.workflow_state
    if state.pending_status in {"plan_complete", "done", "approved", "implementation_complete"}:
        return None
    task = None
    if state.pending_task_id:
        task = ctx.task_service.get(state.pending_task_id)
    if task is not None and state.pending_actor:
        return state.pending_actor, task, task.status.value
    task = ctx.task_service.next_ready_task()
    if task is None:
        return None
    agent = ctx.task_service.default_agent_for_task(task)
    state.pending_task_id = task.id
    state.pending_actor = agent
    state.pending_status = task.status.value
    ctx.workflow_state_repo.save(state)
    return agent, task, task.status.value


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

    def _handler(self, _signum, _frame):
        self.interrupted = True


def handle_interrupt(workspace: Path, handoff_path: Path) -> str:
    """Show interrupt menu and handle user choice."""
    from agent_coordinator.infrastructure.tui import InterruptMenu

    menu = InterruptMenu()
    choice = menu.show()

    if choice == "i":
        # Inspect handoff
        if handoff_path.exists():
            print("\nCurrent handoff.md:")
            print("─" * 60)
            print(handoff_path.read_text())
            print("─" * 60)
        input("\nPress Enter to continue...")
        return handle_interrupt(workspace, handoff_path)

    if choice == "e":
        # Edit handoff directly
        import subprocess

        from agent_coordinator.infrastructure.editor import get_editor

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

        return "c"  # Continue after editing

    if choice == "m":
        # Add message using editor
        message = menu.get_message()
        if message:
            with open(handoff_path, "a") as f:
                f.write(f"\n\n<!-- Human intervention: {message} -->\n")
            print("Message added to handoff.md")
        return "c"

    if choice == "u":
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
    tasks_path = workspace / "tasks.json"
    has_plan = bool(_plan_files(workspace))
    workflow_repo = WorkflowStateRepository(_state_dir(workspace) / WORKFLOW_STATE_FILE)
    workflow_state = workflow_repo.load()
    status_line = "no structured workflow state yet"
    if tasks_path.exists():
        try:
            task_service = TaskService(JsonTaskRepository(tasks_path))
            ready = task_service.ready_queue()
            if workflow_state.pending_task_id and workflow_state.pending_actor:
                status_line = f"task {workflow_state.pending_task_id}  next → {workflow_state.pending_actor}"
            elif ready:
                status_line = f"ready: {ready[0].id} ({ready[0].mode.value})"
            else:
                status_line = "no ready tasks"
        except Exception:
            status_line = "tasks.json parse error"

    summary = f"Workspace: {workspace.name}\n{status_line}"

    options = [
        ("r", "Continue current handoff"),
        ("i", "Inspect handoff.md"),
        ("e", "Edit handoff.md"),
        ("s", "Reset sessions"),
    ]
    if has_plan:
        options.append(("p", "Start adding new tasks from plan"))
    options.append(("q", "Quit"))

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

        store = SessionStore(_state_dir(workspace) / SESSION_FILE)
        store.clear()
        display._append_content(f"  {display._theme.color_success}✓  Sessions cleared\033[0m")
        display._append_content("")
        return _show_startup_popup(display, workspace)

    if choice == "p":
        if _start_task_generation_from_plan(workspace):
            display._append_content(f"  {display._theme.color_success}✓  Next turn set to add tasks from plan\033[0m")
            display._append_content("")
            return "r"
        display._append_content(f"  {display._theme.color_warning}⚠  No plan documents found\033[0m")
        display._append_content("")
        return _show_startup_popup(display, workspace)

    return choice


# ── Coordinator context & helpers ─────────────────────────────────────────────


@dataclasses.dataclass
class _CoordinatorContext:
    """Shared mutable state threaded through every coordinator helper."""

    workspace: Path
    state: Path
    config: dict
    agents: dict
    default_backend: str
    handoff_path: Path
    handoff_reader: HandoffReader
    session_store: SessionStore
    event_log: EventLog
    workflow_state_repo: WorkflowStateRepository
    workflow_state: WorkflowState
    router: WorkflowRouter
    builder: PromptBuilder
    runner_cache: dict[str, AgentRunner]
    task_service: TaskService | None
    display: Any
    interrupt_menu: Any
    verbose: bool
    auto: bool
    stateless: bool
    logger: Any
    turn_counts: dict[str, int] = dataclasses.field(default_factory=dict)
    total_turns: int = 0


def _setup_coordinator(
    workspace: Path,
    max_turns: int,
    reset: bool,
    verbose: bool,
    output_lines: int,
    streaming: bool,
    display: Any,
    auto: bool,
    stateless: bool = False,
) -> _CoordinatorContext | None:
    """Initialise all coordinator state.

    Returns *None* when the user quits from the startup popup (the display is
    already closed in that case).
    """
    state = _state_dir(workspace)
    setup_log(state)
    logger = get_logger()
    logger.info(
        "run_coordinator start",
        extra={
            "ctx": {
                "workspace": str(workspace),
                "max_turns": max_turns,
                "verbose": verbose,
                "streaming": streaming,
                "stateless": stateless,
            }
        },
    )

    config = load_config(workspace)
    agents = load_agent_config(config)
    retry_policy = load_retry_policy(config)
    default_backend = config.get("default_backend", DEFAULT_BACKEND)

    handoff_path = workspace / "handoff.md"
    handoff_reader = HandoffReader(handoff_path)
    session_store = SessionStore(_state_dir(workspace) / SESSION_FILE)
    event_log = EventLog(_state_dir(workspace) / EVENT_LOG_FILE)
    router = WorkflowRouter()
    builder = PromptBuilder(coordinator_dir=COORDINATOR_DIR)

    from agent_coordinator.infrastructure.tui import InterruptMenu, create_display

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

    tasks_path = _bootstrap_tasks(workspace)
    task_service = TaskService(JsonTaskRepository(tasks_path), retry_policy=retry_policy)
    workflow_state_repo = WorkflowStateRepository(_state_dir(workspace) / WORKFLOW_STATE_FILE)
    workflow_state = _initial_workflow_state(workflow_state_repo, handoff_reader, task_service)

    if reset:
        session_store.clear()
        logger.info("session state reset")
        print("Session state reset")

    if not handoff_path.exists():
        print(f"\nHandoff file not found: {handoff_path}")
        print("Creating initial handoff.md...")
        _create_initial_handoff(workspace)
        print()

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
            return None

    return _CoordinatorContext(
        workspace=workspace,
        state=state,
        config=config,
        agents=agents,
        default_backend=default_backend,
        handoff_path=handoff_path,
        handoff_reader=handoff_reader,
        session_store=session_store,
        event_log=event_log,
        workflow_state_repo=workflow_state_repo,
        workflow_state=workflow_state,
        router=router,
        builder=builder,
        runner_cache=runner_cache,
        task_service=task_service,
        display=display,
        interrupt_menu=interrupt_menu,
        verbose=verbose,
        auto=auto,
        stateless=stateless,
        logger=logger,
    )


def _execute_turn(ctx: _CoordinatorContext) -> str:
    """Execute one turn of the coordinator loop.

    Returns ``"break"`` to stop the loop, ``"continue"`` to skip to the next
    iteration, ``"return"`` to exit *run_coordinator* immediately, or ``"ok"``
    on success.
    """
    selection = _select_pending_turn(ctx)
    if selection is None:
        ctx.logger.info("workflow terminal", extra={"ctx": {"reason": "No ready tasks"}})
        print("\nWorkflow complete ✅")
        return "break"

    agent, task, status = selection

    if agent == "human":
        from agent_coordinator.infrastructure.human_prompt import prompt_human_input

        ctx.logger.info("awaiting human input", extra={"ctx": {"task": task.id}})
        action = prompt_human_input(ctx.handoff_path, task.id, status, display=ctx.display)
        if action == "quit":
            ctx.logger.info("human chose quit")
            return "break"
        return "continue"

    if agent not in ctx.agents:
        ctx.logger.error(
            "unknown agent in handoff",
            extra={
                "ctx": {
                    "agent": agent,
                    "known": list(ctx.agents.keys()),
                }
            },
        )
        raise RuntimeError(f"Unknown agent '{agent}'. Known: {', '.join(ctx.agents.keys())}")

    return _run_agent_turn(ctx, agent, task, status)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1.3 tokens per whitespace-delimited word."""
    return int(len(text.split()) * 1.3)


def _record_turn_result(
    ctx: _CoordinatorContext,
    agent: str,
    task: Any,
    status: str,
    t_start: float,
    output_buffer: list[str],
    handoff_updated: bool,
    run_result: Any,
    prompt_file: Path,
    prompt_hash: str,
) -> str:
    """Update structured state from an agent result and return a loop-control signal."""
    ctx.turn_counts[agent] = ctx.turn_counts.get(agent, 0) + 1
    ctx.total_turns += 1
    duration_seconds = round(time.monotonic() - t_start, 2)
    response_text = run_result.text if getattr(run_result, "text", "") else "".join(output_buffer)
    new_message = _extract_agent_message(response_text, ctx.handoff_reader)
    if new_message is None:
        ctx.logger.error("invalid structured response after agent turn", extra={"ctx": {"agent": agent}})
        ctx.display.finish_agent_turn(success=False)
        print(f"\nWARNING: No valid structured handoff block returned by {agent}")
        return "break"

    task_id, previous_task_status, progress = _update_task_from_message(ctx, task.id, agent, new_message)
    new_status = new_message.status.value
    new_next = new_message.next
    transition_key = _transition_key(task_id or task.id, status, new_status, agent)

    ctx.logger.info(
        "agent turn done",
        extra={
            "ctx": {
                "agent": agent,
                "new_status": new_status,
                "next": new_next,
            }
        },
    )
    ctx.display.finish_agent_turn(success=True, new_status=new_status, next_agent=new_next)
    if transition_key not in ctx.workflow_state.transition_keys:
        _append_handoff_log(ctx.handoff_path, new_message)
        ctx.event_log.append(
            turn=ctx.total_turns,
            agent=agent,
            task_id=task_id or task.id,
            status_before=status,
            status_after=new_status,
            session_id=run_result.session_id,
            response_text=response_text[:50_000],
            prompt_file=str(prompt_file.relative_to(ctx.state)),
            prompt_hash=prompt_hash,
            duration_seconds=duration_seconds,
            extra={
                "transition_key": transition_key,
                "prompt_tokens_est": _estimate_tokens(prompt_file.read_text(errors="replace")) if prompt_file.exists() else 0,
                "response_tokens_est": _estimate_tokens(response_text),
            },
        )
        ctx.workflow_state.transition_keys.append(transition_key)
        ctx.workflow_state.last_transition_key = transition_key
    ctx.workflow_state.pending_task_id = task_id or task.id
    ctx.workflow_state.pending_actor = "" if new_next in ("none", "human") else new_next
    ctx.workflow_state.pending_status = previous_task_status or new_status
    ctx.workflow_state.pending_summary = new_message.summary
    if new_status in {"approved", "done", "plan_complete", "implementation_complete"} or new_next == "none":
        ctx.workflow_state.pending_task_id = ""
        ctx.workflow_state.pending_actor = ""
    if new_next == "human":
        ctx.workflow_state.pending_actor = "human"
    ctx.workflow_state.no_progress_turns = 0 if progress else ctx.workflow_state.no_progress_turns + 1
    if ctx.workflow_state.no_progress_turns >= 2:
        _recover_from_coordination_loop(ctx)
    else:
        ctx.workflow_state_repo.save(ctx.workflow_state)
    del response_text  # free the potentially large string

    time.sleep(1)
    return "ok"


def _run_agent_turn(ctx: _CoordinatorContext, agent: str, task: Any, status: str) -> str:
    """Dispatch a single agent turn and record results.

    Returns ``"break"``, ``"return"``, or ``"ok"``.
    """
    agent_cfg = ctx.agents[agent]
    if agent not in ctx.runner_cache:
        r = create_runner_for_agent(agent_cfg, ctx.default_backend, ctx.verbose)
        from agent_coordinator.infrastructure.manual_runner import ManualRunner

        if isinstance(r, ManualRunner) and hasattr(ctx.display, "read_input"):
            r._input_fn = ctx.display.read_input
        ctx.runner_cache[agent] = r
    runner = ctx.runner_cache[agent]
    backend_name = agent_cfg.get("backend", ctx.default_backend)
    use_stateless_mode = ctx.stateless and agent_supports_stateless_mode(agent, agent_cfg)

    first_turn = True if use_stateless_mode else ctx.session_store.get(agent) is None
    state_summary = (
        f"Structured workflow state\n"
        f"- Current task: {task.id}\n"
        f"- Mode: {task.mode.value}\n"
        f"- Expected outputs: {', '.join(expected_outputs_for_mode(task.mode))}\n"
        f"- Pending summary: {ctx.workflow_state.pending_summary or 'none'}\n"
    )
    prompt = ctx.builder.build(agent, ctx.workspace, state_summary, agent_cfg, task, first_turn)

    # ── Prompt persistence (1.2) ──────────────────────────────────────
    turn_num = ctx.total_turns + 1
    prompts_log_dir = ctx.state / "prompts_log"
    prompts_log_dir.mkdir(exist_ok=True)
    prompt_file = prompts_log_dir / f"turn-{turn_num:03d}-{agent}.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    ctx.logger.info(
        "agent turn start",
        extra={
            "ctx": {
                "agent": agent,
                "backend": backend_name,
                "task": task.id,
                "status": status,
                "turn": ctx.total_turns + 1,
            }
        },
    )
    ctx.display.start_agent_turn(agent, backend_name, task.id, status)

    # ── Output capture (1.1) and timing (1.3) ────────────────────────
    output_buffer: list[str] = []

    def _on_output(chunk: str, _buf: list[str] = output_buffer) -> None:
        _buf.append(chunk)
        if ctx.verbose:
            ctx.display.update_output(chunk)

    t_start = time.monotonic()
    run_result = None
    handoff_updated = False
    for attempt in range(1 + DEFAULT_HANDOFF_RETRIES):
        try:
            run_result = runner.run(
                message=prompt if attempt == 0 else _retry_prompt(agent, ctx.workspace),
                workspace=ctx.workspace,
                session_id=None if use_stateless_mode else ctx.session_store.get(agent),
                model=agent_cfg.get("model"),
                on_output=_on_output,
            )
        except RuntimeError as e:
            ctx.logger.error(
                "backend error",
                extra={
                    "ctx": {
                        "agent": agent,
                        "attempt": attempt,
                        "error": str(e),
                    }
                },
            )
            ctx.display.finish_agent_turn(success=False)
            choice = _show_backend_error(ctx.display, e, ctx.workspace)
            if choice == "e":
                # Reload agents after editing
                ctx.config = load_config(ctx.workspace)
                ctx.agents = load_agent_config(ctx.config)
                ctx.runner_cache.clear()
            if choice == "q":
                return "return"
            # retry or reloaded config — break out of attempt loop and re-run the turn
            break

        if not use_stateless_mode:
            ctx.session_store.set(agent, run_result.session_id)
        if _extract_agent_message(run_result.text, ctx.handoff_reader) is not None:
            handoff_updated = True
            break

        if attempt < DEFAULT_HANDOFF_RETRIES:
            ctx.logger.warning(
                "handoff not updated, retrying",
                extra={
                    "ctx": {
                        "agent": agent,
                        "attempt": attempt + 1,
                    }
                },
            )
            print(f"handoff.md not updated - retrying ({attempt + 1}/{DEFAULT_HANDOFF_RETRIES})")

    return _record_turn_result(
        ctx,
        agent,
        task,
        status,
        t_start,
        output_buffer,
        handoff_updated,
        run_result,
        prompt_file,
        prompt_hash,
    )


def _handle_interrupt(ctx: _CoordinatorContext) -> str:
    """Handle a KeyboardInterrupt.  Returns ``"quit"`` or ``"continue"``."""
    ctx.logger.info("KeyboardInterrupt — showing interrupt menu")
    choice = None
    while True:
        choice = ctx.interrupt_menu.show()
        if choice == "q":
            ctx.logger.info("user quit via interrupt menu")
            break
        if choice in ("c", "r"):
            break
        if choice == "t":
            _handle_pause(ctx)
            break
        if not _handle_interrupt_action(choice, ctx):
            break  # unknown choice — continue execution
    return "quit" if choice == "q" else "continue"


def _handle_pause(ctx: _CoordinatorContext) -> None:
    """Enter pause mode until the user resumes or quits."""
    ctx.logger.info("user paused execution")
    ctx.display.set_paused(True)
    ctx.display._append_content(
        f"  {ctx.display._theme.color_warning}⏸  Execution paused — Ctrl+C to resume or quit\033[0m"
    )
    try:
        while True:
            try:
                time.sleep(0.5)
            except KeyboardInterrupt:  # noqa: PERF203
                resume_choice = ctx.interrupt_menu.show()
                if resume_choice == "q":
                    ctx.display.set_paused(False)
                    ctx.logger.info("user quit from paused state")
                    raise _QuitSignalError() from None
                if resume_choice == "c":
                    break
                _handle_pause_action(resume_choice, ctx)
    except _QuitSignalError:
        return
    ctx.display.set_paused(False)
    ctx.display._append_content(f"  {ctx.display._theme.color_success}▶  Execution resumed\033[0m")
    ctx.logger.info("user resumed execution")


def _handle_pause_action(resume_choice: str, ctx: _CoordinatorContext) -> None:
    """Handle a non-flow-control action during pause."""
    if resume_choice == "e":
        if hasattr(ctx.display, "with_editor"):
            ctx.display.with_editor(ctx.workspace / "handoff.md")
    elif resume_choice == "i":
        hp = ctx.workspace / "handoff.md"
        if hp.exists():
            for ln in hp.read_text().splitlines()[-30:]:
                ctx.display._append_content("  " + ln)
    elif resume_choice == "m":
        user_msg = ctx.interrupt_menu.get_message()
        if user_msg:
            with open(ctx.workspace / "handoff.md", "a") as _f:
                _f.write(f"\n\n<!-- Human intervention: {user_msg} -->\n")
    elif resume_choice in ("n", "s", "l", "w", "x"):
        _handle_popup_command(resume_choice, ctx.workspace, ctx.display)


def _handle_interrupt_action(choice: str, ctx: _CoordinatorContext) -> bool:
    """Handle a non-flow-control interrupt menu action.

    Returns ``True`` if the action was recognised (menu should re-show),
    ``False`` for an unknown choice (caller should break).
    """
    if choice in ("n", "s", "l", "w", "x"):
        _handle_popup_command(choice, ctx.workspace, ctx.display)
        return True
    if choice == "m":
        user_msg = ctx.interrupt_menu.get_message()
        if user_msg:
            with open(ctx.workspace / "handoff.md", "a") as _f:
                _f.write(f"\n\n<!-- Human intervention: {user_msg} -->\n")
        return True
    if choice == "e":
        if hasattr(ctx.display, "with_editor"):
            ctx.display.with_editor(ctx.workspace / "handoff.md")
        else:
            import subprocess as _sp

            from agent_coordinator.infrastructure.editor import get_editor

            try:
                _sp.run([get_editor(), str(ctx.workspace / "handoff.md")], check=True)
            except Exception as _e:
                ctx.display._append_content(f"  Editor error: {_e}")
        return True
    if choice == "i":
        hp = ctx.workspace / "handoff.md"
        if hp.exists():
            for ln in hp.read_text().splitlines()[-30:]:
                ctx.display._append_content("  " + ln)
        return True
    return False


def _handle_crash(display: Any, workspace: Path, exc: Exception) -> None:
    """Handle an unhandled exception in the coordinator loop."""
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
                if hasattr(display, "with_editor"):
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


def run_coordinator(
    workspace: Path,
    max_turns: int,
    reset: bool,
    verbose: bool,
    output_lines: int = 10,
    streaming: bool = True,
    display=None,
    auto: bool = False,
    stateless: bool = False,
) -> None:
    ctx = _setup_coordinator(workspace, max_turns, reset, verbose, output_lines, streaming, display, auto, stateless)
    if ctx is None:
        return

    try:
        while max_turns == 0 or ctx.total_turns < max_turns:
            try:
                result = _execute_turn(ctx)
                if result == "break":
                    break
                if result == "return":
                    return
            except KeyboardInterrupt:
                if _handle_interrupt(ctx) == "quit":
                    break
        else:
            ctx.logger.info("max turns reached", extra={"ctx": {"max_turns": max_turns}})
            print(f"\nReached max turns ({max_turns})")

    except Exception as exc:
        _handle_crash(ctx.display, ctx.workspace, exc)
    finally:
        ctx.display.close()
        ctx.logger.info("=== session end ===", extra={"ctx": {"total_turns": ctx.total_turns}})

    _print_summary(ctx.total_turns, ctx.turn_counts)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _show_backend_error(display: Screen, exc: Exception, workspace: Path) -> str:
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


def _print_header(workspace: Path, max_turns: int, agents: dict) -> None:
    print(f"\n{'─' * 60}")
    print(f"  Coordination workspace: {workspace}")
    print(f"  Max turns:  {'unlimited' if max_turns == 0 else max_turns}")
    print(f"  Agents:     {', '.join(agents.keys())}")
    print(f"{'─' * 60}\n")


def _print_summary(total_turns: int, turn_counts: dict[str, int]) -> None:
    print(f"\n{'─' * 60}")
    print(f"  Total turns: {total_turns}")
    for agent, count in sorted(turn_counts.items()):
        print(f"  {agent.capitalize()} turns: {count}")
    print(f"{'─' * 60}")


# ── Entry point ───────────────────────────────────────────────────────────────


def _create_initial_handoff(workspace: Path) -> None:
    """Create an initial handoff.md (and default agents.json if absent) in the workspace."""
    workspace.mkdir(parents=True, exist_ok=True)
    _bootstrap_tasks(workspace)

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

    agents_path = workspace / AGENTS_FILE
    if not agents_path.exists():
        default_agents_cfg = {
            "default_backend": DEFAULT_BACKEND,
            "retry_policy": {
                "max_rework": 3,
                "on_exceed": "needs_human",
            },
            "agents": {
                "architect": {
                    "prompt_file": "prompts/architect.md",
                    "backend": "copilot",
                    "model": "claude-sonnet-4.6",
                    "supportsStatelessMode": False,
                },
                "developer": {
                    "prompt_file": "prompts/developer.md",
                    "backend": "copilot",
                    "model": "claude-sonnet-4.6",
                    "supportsStatelessMode": True,
                },
                "qa_engineer": {
                    "prompt_file": "prompts/qa_engineer.md",
                    "backend": "copilot",
                    "model": "claude-sonnet-4.6",
                    "supportsStatelessMode": True,
                },
            },
        }
        agents_path.write_text(json.dumps(default_agents_cfg, indent=4))
        print(f"Created default agents.json in {workspace}")


def _do_startup_init(action: dict, _args: argparse.Namespace) -> None:
    workspace = action.get("workspace", Path(DEFAULT_WORKSPACE).resolve())
    screen = action.get("screen")
    workspace.mkdir(parents=True, exist_ok=True)
    _create_initial_handoff(workspace)
    if screen:
        t = screen._theme
        screen._append_content(f"  {t.color_success}✓  Workspace initialised: {workspace}\033[0m")
        screen._append_content(f"  {t.text_dim}Run /run {workspace} to start\033[0m")
    else:
        print(f"\n  Workspace initialised: {workspace}")
        print(f"  Run:  agent-coordinator --workspace {workspace}\n")


def _do_startup_import(action: dict, args: argparse.Namespace) -> None:
    from agent_coordinator.helpers.import_plan import import_document

    workspace = action.get("workspace", Path(DEFAULT_WORKSPACE).resolve())
    screen = action.get("screen")
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


def _do_startup_run(action: dict, args: argparse.Namespace) -> None:
    workspace = action.get("workspace", Path(DEFAULT_WORKSPACE).resolve())
    screen = action.get("screen")
    _run_from_workspace(workspace, args, display=screen)


def _do_startup_reset(action: dict, _args: argparse.Namespace) -> None:
    from agent_coordinator.infrastructure.session_store import SessionStore

    workspace = action.get("workspace", Path(DEFAULT_WORKSPACE).resolve())
    screen = action.get("screen")
    store = SessionStore(_state_dir(workspace) / SESSION_FILE)
    store.clear()
    if screen:
        t = screen._theme
        screen._append_content(f"  {t.color_success}✓  Session state cleared for: {workspace}\033[0m")
    else:
        print(f"\n  Session state cleared for: {workspace}\n")


def _do_startup_quit(action: dict, _args: argparse.Namespace) -> None:
    screen = action.get("screen")
    if screen and screen._active:
        screen.close()


_STARTUP_DISPATCH: dict[str, Callable] = {
    "init": _do_startup_init,
    "import": _do_startup_import,
    "run": _do_startup_run,
    "reset": _do_startup_reset,
    "quit": _do_startup_quit,
}


def _execute_startup_action(action: dict, args: argparse.Namespace) -> None:
    """Execute an action returned by StartupCLI.run()."""
    handler = _STARTUP_DISPATCH.get(action["action"])
    if handler:
        handler(action, args)


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

    if key == "n":  # /init
        path_raw = (
            display.read_input("Workspace path: ") if hasattr(display, "read_input") else input("Workspace path: ")
        )
        new_ws = Path(path_raw).resolve() if path_raw else workspace
        new_ws.mkdir(parents=True, exist_ok=True)
        _create_initial_handoff(new_ws)
        _info(f"Workspace initialised: {new_ws}")

    elif key == "s":  # /import-spec
        _run_import(display, "spec", workspace, _info, _warn)

    elif key == "l":  # /import-plan
        _run_import(display, "plan", workspace, _info, _warn)

    elif key == "w":  # /run (switch workspace)
        path_raw = (
            display.read_input("Workspace path: ") if hasattr(display, "read_input") else input("Workspace path: ")
        )
        if path_raw:
            new_ws = Path(path_raw).resolve()
            _info(f"Switching to {new_ws} — restart required (use --workspace)")
        else:
            _warn("No path entered — staying on current workspace")

    elif key == "x":  # /reset
        from agent_coordinator.infrastructure.session_store import SessionStore

        store = SessionStore(_state_dir(workspace) / SESSION_FILE)
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
            stateless=args.stateless,
        )
    except SystemExit:
        raise
    except Exception as exc:
        from agent_coordinator.infrastructure.diagnostic_log import log_crash, log_path

        log_crash(exc, context="startup-run")
        from agent_coordinator.infrastructure.tui import _classify_error

        title, friendly = _classify_error(exc)
        w = 60
        print(f"\n{'═' * w}", file=sys.stderr)
        print(f"  {title}", file=sys.stderr)
        for line in friendly.splitlines():
            print(f"  {line}", file=sys.stderr)
        lp = log_path()
        if lp:
            print(f"  Log: {lp}", file=sys.stderr)
        print(f"{'═' * w}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrate multi-agent AI workflows via handoff.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agent-coordinator                                    # interactive startup menu
  agent-coordinator --import SPECIFICATION.md          # import spec
  agent-coordinator --import-specs ./specs/            # import folder of specs
  agent-coordinator --import-plans ./plans/            # import folder of plans
  agent-coordinator --workspace ./my-project           # run coordinator
  agent-coordinator --workspace ./my-feature --reset   # reset sessions
""",
    )

    # ── Workflow arguments ────────────────────────────────────────────────────
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help="Directory containing handoff.md and project files (default: workspace/)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help="Maximum agent turns before stopping (0 = unlimited, default: 0)",
    )
    parser.add_argument("--reset", action="store_true", help="Clear saved session IDs and start fresh")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-turn output")
    parser.add_argument(
        "--output-lines", type=int, default=10, help="Lines of agent output to show in the TUI window (default: 10)"
    )
    parser.add_argument(
        "--no-streaming", action="store_true", help="Print agent output all at once instead of streaming it"
    )
    parser.add_argument("--auto", action="store_true", help="Skip the startup menu and run immediately")
    parser.add_argument(
        "--stateless",
        action="store_true",
        help="Run agents without session persistence (fresh context every turn)",
    )

    # ── Import arguments ──────────────────────────────────────────────────────
    parser.add_argument(
        "--import",
        dest="import_file",
        type=Path,
        metavar="FILE",
        help="Import a specification or implementation plan into --workspace",
    )
    parser.add_argument(
        "--type", choices=["spec", "plan"], default=None, help="Document type for --import (default: auto-detect)"
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files when importing")
    parser.add_argument("--no-handoff", action="store_true", help="Skip creating handoff.md when importing")
    parser.add_argument("--no-tasks", action="store_true", help="Skip creating tasks.json when importing a plan")
    parser.add_argument(
        "--import-specs",
        dest="import_specs",
        type=Path,
        metavar="PATH",
        help="Import a directory (or file) of specification docs into <workspace>/specs/",
    )
    parser.add_argument(
        "--import-plans",
        dest="import_plans",
        type=Path,
        metavar="PATH",
        help="Import a directory (or file) of implementation plans into <workspace>/plans/",
    )

    args = parser.parse_args()

    # ── Startup CLI (no explicit workspace or import given) ───────────────────
    _explicit_workspace = "--workspace" in sys.argv or "-w" in sys.argv
    _has_action = args.import_file or args.import_specs or args.import_plans or _explicit_workspace or args.reset

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

    if args.import_specs:
        from agent_coordinator.helpers.import_plan import import_folder

        source = args.import_specs.resolve()
        if not args.quiet:
            print(f"\nImporting specs from: {source}")
            print(f"Workspace: {workspace}")
            print()
        import_folder(
            source=source,
            workspace=workspace,
            doc_type="spec",
            force=args.force,
            no_handoff=args.no_handoff,
            verbose=not args.quiet,
        )
        if not args.quiet:
            print("Done. Run the coordinator to start:")
            print(f"  agent-coordinator --workspace {workspace}")
        return

    if args.import_plans:
        from agent_coordinator.helpers.import_plan import import_folder

        source = args.import_plans.resolve()
        if not args.quiet:
            print(f"\nImporting plans from: {source}")
            print(f"Workspace: {workspace}")
            print()
        import_folder(
            source=source,
            workspace=workspace,
            doc_type="plan",
            force=args.force,
            no_handoff=args.no_handoff,
            no_tasks=args.no_tasks,
            verbose=not args.quiet,
        )
        if not args.quiet:
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
            stateless=args.stateless,
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
        print(f"\n{'═' * w}", file=sys.stderr)
        print(f"  {title}", file=sys.stderr)
        print(f"{'─' * w}", file=sys.stderr)
        for line in friendly.splitlines():
            print(f"  {line}", file=sys.stderr)
        if lp:
            print(f"{'─' * w}", file=sys.stderr)
            print(f"  Log: {lp}", file=sys.stderr)
        print(f"{'═' * w}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
