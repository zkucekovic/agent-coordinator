#!/usr/bin/env python3
"""
coordinator.py — orchestrates multi-agent OpenCode sessions via handoff.md.

Agent configuration lives in agents.json in the workspace directory.
See README.md for full usage documentation.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from src.application.prompt_builder import PromptBuilder
from src.application.router import WorkflowRouter
from src.application.task_service import TaskService
from src.domain.retry_policy import RetryPolicy
from src.infrastructure.event_log import EventLog
from src.infrastructure.handoff_reader import HandoffReader
from src.infrastructure.opencode_runner import OpenCodeRunner
from src.infrastructure.session_store import SessionStore
from src.infrastructure.task_repository import JsonTaskRepository

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_WORKSPACE = Path(__file__).parent.resolve() / "workspace"
DEFAULT_MAX_TURNS = 30
SESSION_FILE = ".coordinator_sessions.json"
EVENT_LOG_FILE = "workflow_events.jsonl"
AGENTS_FILE = "agents.json"

_DEFAULT_AGENTS: dict = {
    "architect":   {"model": None, "prompt_file": "prompts/architect.md"},
    "developer":   {"model": None, "prompt_file": "prompts/developer.md"},
    "qa_engineer": {"model": None, "prompt_file": "prompts/qa_engineer.md"},
}

# ── Config loading ────────────────────────────────────────────────────────────

def load_agent_config(workspace: Path) -> dict:
    """Load agents.json, falling back to built-in defaults."""
    import json
    path = workspace / AGENTS_FILE
    if path.exists():
        data = json.loads(path.read_text())
        return data.get("agents", data)
    return _DEFAULT_AGENTS


def load_retry_policy(workspace: Path) -> RetryPolicy:
    """Load retry_policy from agents.json if present, else use defaults."""
    import json
    path = workspace / AGENTS_FILE
    if path.exists():
        data = json.loads(path.read_text())
        if "retry_policy" in data:
            return RetryPolicy.from_dict(data["retry_policy"])
    return RetryPolicy()


# ── Coordinator loop ──────────────────────────────────────────────────────────

def run_coordinator(workspace: Path, max_turns: int, reset: bool, verbose: bool) -> None:
    agents = load_agent_config(workspace)
    retry_policy = load_retry_policy(workspace)

    handoff_reader = HandoffReader(workspace / "handoff.md")
    session_store = SessionStore(workspace / SESSION_FILE)
    event_log = EventLog(workspace / EVENT_LOG_FILE)
    runner = OpenCodeRunner(verbose=verbose)
    router = WorkflowRouter()
    builder = PromptBuilder()

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

        try:
            run_result = runner.run(
                message=prompt,
                workspace=workspace,
                session_id=session_store.get(agent),
                model=agent_cfg.get("model"),
            )
        except RuntimeError as e:
            print(f"\n❌  OpenCode error: {e}")
            sys.exit(1)

        session_store.set(agent, run_result.session_id)
        turn_counts[agent] = turn_counts.get(agent, 0) + 1
        total_turns += 1

        new_message = handoff_reader.read()
        if new_message is None or new_message == message:
            print(f"\n⚠  WARNING: handoff.md was not updated by {agent}. Check agent output.")
            break

        new_status = new_message.status.value
        new_next = new_message.next
        print(f"  ✓ handoff.md updated → status={new_status}, next={new_next}")

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

