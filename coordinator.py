#!/usr/bin/env python3
"""
coordinator.py — orchestrates multi-agent OpenCode sessions via handoff.md.

Agent configuration lives in agents.json in the workspace directory.
See README.md for full usage documentation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from src.application.prompt_builder import PromptBuilder
from src.application.router import WorkflowRouter
from src.application.task_service import TaskService
from src.domain.models import HandoffStatus, TaskStatus
from src.domain.retry_policy import RetryPolicy
from src.infrastructure.event_log import EventLog
from src.infrastructure.handoff_reader import HandoffReader
from src.infrastructure.opencode_runner import OpenCodeRunner
from src.infrastructure.session_store import SessionStore
from src.infrastructure.task_repository import JsonTaskRepository

# ── Constants ─────────────────────────────────────────────────────────────────

COORDINATOR_DIR = Path(__file__).parent.resolve()
DEFAULT_WORKSPACE = COORDINATOR_DIR / "workspace"
DEFAULT_MAX_TURNS = 30
DEFAULT_HANDOFF_RETRIES = 1
SESSION_FILE = ".coordinator_sessions.json"
EVENT_LOG_FILE = "workflow_events.jsonl"
AGENTS_FILE = "agents.json"

_DEFAULT_AGENTS: dict = {
    "architect":   {"model": None, "prompt_file": "prompts/architect.md"},
    "developer":   {"model": None, "prompt_file": "prompts/developer.md"},
    "qa_engineer": {"model": None, "prompt_file": "prompts/qa_engineer.md"},
}

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
    """Load and return the full agents.json content, or an empty dict."""
    path = workspace / AGENTS_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {}


def load_agent_config(config: dict) -> dict:
    """Extract agent definitions from pre-loaded config."""
    return config.get("agents", _DEFAULT_AGENTS) if config else dict(_DEFAULT_AGENTS)


def load_retry_policy(config: dict) -> RetryPolicy:
    """Extract retry policy from pre-loaded config."""
    if config and "retry_policy" in config:
        return RetryPolicy.from_dict(config["retry_policy"])
    return RetryPolicy()


# ── Task status sync ─────────────────────────────────────────────────────────

def _sync_task_status(
    task_service: TaskService | None,
    task_id: str,
    handoff_status: HandoffStatus,
    verbose: bool,
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
    try:
        task_service.update_status(task_id, target)
        if verbose:
            print(f"  ↳ tasks.json: {task_id} → {target.value}")
    except ValueError:
        # Transition not valid from current state — skip silently.
        pass


# ── Handoff file content hash ────────────────────────────────────────────────

def _file_hash(path: Path) -> str:
    """Return a hex digest of a file's content, or empty string if missing."""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Coordinator loop ──────────────────────────────────────────────────────────

def run_coordinator(workspace: Path, max_turns: int, reset: bool, verbose: bool) -> None:
    config = load_config(workspace)
    agents = load_agent_config(config)
    retry_policy = load_retry_policy(config)

    handoff_path = workspace / "handoff.md"
    handoff_reader = HandoffReader(handoff_path)
    session_store = SessionStore(workspace / SESSION_FILE)
    event_log = EventLog(workspace / EVENT_LOG_FILE)
    runner = OpenCodeRunner(verbose=verbose)
    router = WorkflowRouter()
    builder = PromptBuilder(coordinator_dir=COORDINATOR_DIR)

    tasks_path = workspace / "tasks.json"
    task_service = (
        TaskService(JsonTaskRepository(tasks_path), retry_policy=retry_policy)
        if tasks_path.exists()
        else None
    )

    if reset:
        session_store.clear()
        print("⚠  Session state reset — starting fresh sessions.")

    turn_counts: dict[str, int] = {}
    total_turns = 0

    _print_header(workspace, max_turns, agents)

    while total_turns < max_turns:
        message = handoff_reader.read()
        if message is None:
            print("❌  No valid handoff block found. Please initialize handoff.md.")
            sys.exit(1)

        decision = router.route(message)
        status = message.status.value
        print(f"\n[Turn {total_turns + 1}] status={status}  next={decision.next_actor}  task={message.task_id}")

        if decision.is_terminal:
            print(f"\n{decision.stop_reason}")
            break

        agent = decision.next_actor
        if agent not in agents:
            print(f"\n❓  Unknown agent: {agent!r}")
            print(f"   Known agents: {', '.join(agents.keys())}")
            print(f"   Add '{agent}' to agents.json, then re-run.")
            sys.exit(1)

        agent_cfg = agents[agent]
        next_task = task_service.next_ready_task() if task_service else None
        first_turn = session_store.get(agent) is None
        prompt = builder.build(agent, workspace, handoff_reader.read_raw(), agent_cfg, next_task, first_turn)

        print(f"  Agent: {agent.upper()}")
        if verbose:
            print(f"  {'─'*40}")

        hash_before = _file_hash(handoff_path)
        handoff_updated = False

        for attempt in range(1 + DEFAULT_HANDOFF_RETRIES):
            try:
                run_result = runner.run(
                    message=prompt if attempt == 0 else _retry_prompt(agent, workspace),
                    workspace=workspace,
                    session_id=session_store.get(agent),
                    model=agent_cfg.get("model"),
                )
            except RuntimeError as e:
                print(f"\n❌  OpenCode error: {e}")
                sys.exit(1)

            session_store.set(agent, run_result.session_id)
            hash_after = _file_hash(handoff_path)

            if hash_after != hash_before:
                handoff_updated = True
                break

            if attempt < DEFAULT_HANDOFF_RETRIES:
                print(f"  ⚠  handoff.md not updated — retrying ({attempt + 1}/{DEFAULT_HANDOFF_RETRIES})")

        turn_counts[agent] = turn_counts.get(agent, 0) + 1
        total_turns += 1

        if not handoff_updated:
            print(f"\n⚠  WARNING: handoff.md was not updated by {agent} after retries. Check agent output.")
            break

        new_message = handoff_reader.read()
        if new_message is None:
            print(f"\n⚠  WARNING: handoff.md has no valid block after {agent}'s turn.")
            break

        new_status = new_message.status.value
        new_next = new_message.next
        print(f"  ✓ handoff.md updated → status={new_status}, next={new_next}")

        _sync_task_status(task_service, new_message.task_id, new_message.status, verbose)

        event_log.append(
            turn=total_turns,
            agent=agent,
            task_id=message.task_id,
            status_before=status,
            status_after=new_status,
            session_id=run_result.session_id,
        )

        time.sleep(1)

    else:
        print(f"\n⚠  Reached max turns ({max_turns}). Stopping.")

    _print_summary(total_turns, turn_counts)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _retry_prompt(agent: str, workspace: Path) -> str:
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

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drive multi-agent OpenCode sessions via handoff.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 coordinator.py
  python3 coordinator.py --workspace /path/to/project
  python3 coordinator.py --reset
  python3 coordinator.py --max-turns 5 --quiet
""",
    )
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    if not (workspace / "handoff.md").exists():
        print(f"❌  handoff.md not found in {workspace}")
        sys.exit(1)

    run_coordinator(
        workspace=workspace,
        max_turns=args.max_turns,
        reset=args.reset,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()

