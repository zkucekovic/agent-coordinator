#!/usr/bin/env python3
"""
coordinator.py — drives Architect and Engineer OpenCode sessions
using handoff.md as the shared communication channel.

Usage:
    python3 coordinator.py [--workspace PATH] [--max-turns N]
                           [--architect-model PROVIDER/MODEL]
                           [--engineer-model PROVIDER/MODEL]
                           [--reset]

The coordinator:
  1. Reads the NEXT field from the latest handoff block
  2. Sends a turn prompt to the appropriate OpenCode session
  3. Waits for the agent to write its handoff block to handoff.md
  4. Routes to the next agent
  5. Stops when status is plan_complete, needs_human, or blocked
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_WORKSPACE = Path(__file__).parent.resolve()
DEFAULT_MAX_TURNS = 30
DEFAULT_ARCHITECT_MODEL = None  # uses opencode's configured default
DEFAULT_ENGINEER_MODEL = None

SESSION_FILE = ".coordinator_sessions.json"

STOP_STATUSES = {"plan_complete", "needs_human", "blocked"}

# ── Session persistence ────────────────────────────────────────────────────────

def load_sessions(workspace: Path) -> dict:
    path = workspace / SESSION_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_sessions(workspace: Path, sessions: dict) -> None:
    path = workspace / SESSION_FILE
    path.write_text(json.dumps(sessions, indent=2))


# ── Handoff parsing ────────────────────────────────────────────────────────────

def get_latest_block_fields(workspace: Path) -> dict:
    """
    Extract fields from the last valid ---HANDOFF--- block.
    Returns dict with keys: next, status, task_id, role. Empty dict if none found.
    """
    content = (workspace / "handoff.md").read_text()
    blocks = re.findall(r"---HANDOFF---(.*?)---END---", content, re.DOTALL)
    if not blocks:
        return {}
    last = blocks[-1]
    result = {}
    for field in ("NEXT", "STATUS", "TASK_ID", "ROLE"):
        m = re.search(rf"^{field}:\s*(.+)$", last, re.MULTILINE)
        if m:
            result[field.lower()] = m.group(1).strip()
    return result


# ── OpenCode runner ───────────────────────────────────────────────────────────

def run_opencode(
    message: str,
    workspace: Path,
    session_id: str | None = None,
    model: str | None = None,
    verbose: bool = True,
) -> tuple[str, str]:
    """
    Run opencode non-interactively.
    Returns (session_id, full_text_response).
    """
    cmd = [
        "opencode", "run", message,
        "--format", "json",
        "--dir", str(workspace),
    ]
    if session_id:
        cmd += ["--continue", "--session", session_id]
    if model:
        cmd += ["--model", model]

    if verbose:
        print(f"  → running opencode {'(new session)' if not session_id else f'(session {session_id[:12]}…)'}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    text_parts = []
    sid = session_id
    errors = []

    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
            etype = event.get("type", "")
            if etype == "text":
                chunk = event["part"]["text"]
                text_parts.append(chunk)
                if verbose:
                    print(chunk, end="", flush=True)
            elif etype in ("error", "assistant_error"):
                errors.append(str(event))
            if not sid and "sessionID" in event:
                sid = event["sessionID"]
        except json.JSONDecodeError:
            pass

    if verbose and text_parts:
        print()  # newline after streamed output

    if result.returncode != 0 and not text_parts:
        stderr = result.stderr.strip()
        raise RuntimeError(f"opencode exited {result.returncode}: {stderr}")

    return sid, "".join(text_parts)


# ── Turn prompts ──────────────────────────────────────────────────────────────

def build_turn_prompt(
    role: str,
    workspace: Path,
    fields: dict,
    first_turn: bool,
) -> str:
    """Build the message sent to an agent for one turn."""
    handoff_content = (workspace / "handoff.md").read_text()

    role_prompt = (workspace / "prompts" / f"{role}.md").read_text()
    shared_rules = (workspace / "prompts" / "shared_rules.md").read_text()

    task_hint = f"(current task: {fields.get('task_id', 'unknown')})" if fields.get("task_id") else ""

    if first_turn:
        intro = f"""You are the **{role.upper()} agent** for this project. Your working directory is `{workspace}`.

{role_prompt}

---

{shared_rules}

---
"""
    else:
        intro = f"You are the **{role.upper()} agent**. Your working directory is `{workspace}`.\n\n"

    return f"""{intro}
## Current state of handoff.md {task_hint}

```
{handoff_content}
```

---

Read the latest `---HANDOFF---` block above. `NEXT: {role}` — it is your turn.

Take your action now:
- Work in `{workspace}` (read and write files as needed)
- Append your handoff entry to `{workspace}/handoff.md`
- End with a valid `---HANDOFF---` … `---END---` block
"""


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_coordinator(
    workspace: Path,
    max_turns: int,
    architect_model: str | None,
    engineer_model: str | None,
    reset: bool,
    verbose: bool,
) -> None:
    sessions = {} if reset else load_sessions(workspace)
    if reset:
        print("⚠  Session state reset — starting fresh sessions.")

    turn_counts = {"architect": 0, "engineer": 0}
    total_turns = 0

    print(f"\n{'─'*60}")
    print(f"  Coordination workspace: {workspace}")
    print(f"  Max turns: {max_turns}")
    print(f"  Architect model: {architect_model or 'default'}")
    print(f"  Engineer model:  {engineer_model or 'default'}")
    print(f"{'─'*60}\n")

    while total_turns < max_turns:
        fields = get_latest_block_fields(workspace)
        if not fields:
            print("❌  No valid handoff block found in handoff.md. Please initialize the file.")
            sys.exit(1)

        next_actor = fields.get("next", "").lower()
        status = fields.get("status", "").lower()
        task_id = fields.get("task_id", "?")

        print(f"\n[Turn {total_turns + 1}] status={status}  next={next_actor}  task={task_id}")

        # ── Stop conditions ──
        if status in STOP_STATUSES:
            if status == "plan_complete":
                print("\n✅  PLAN COMPLETE — workflow finished successfully.")
            elif status == "needs_human":
                print("\n⚠  NEEDS HUMAN — agent requires human input. Check handoff.md for details.")
            elif status == "blocked":
                print("\n🛑  BLOCKED — workflow is blocked. Check handoff.md for details.")
            break

        if next_actor == "none":
            print("\n✅  NEXT: none — workflow is done.")
            break

        if next_actor == "human":
            print("\n⚠  NEXT: human — pausing for human operator. Edit handoff.md then re-run.")
            break

        if next_actor not in ("architect", "engineer"):
            print(f"\n❓  Unknown next actor: {next_actor!r}. Stopping.")
            break

        # ── Build prompt ──
        model = architect_model if next_actor == "architect" else engineer_model
        first_turn = next_actor not in sessions
        prompt = build_turn_prompt(next_actor, workspace, fields, first_turn)

        print(f"  Agent: {next_actor.upper()}")
        if verbose:
            print(f"  {'─'*40}")

        # ── Run the agent ──
        try:
            session_id, response = run_opencode(
                message=prompt,
                workspace=workspace,
                session_id=sessions.get(next_actor),
                model=model,
                verbose=verbose,
            )
        except RuntimeError as e:
            print(f"\n❌  OpenCode error: {e}")
            sys.exit(1)

        # ── Persist session ID ──
        sessions[next_actor] = session_id
        save_sessions(workspace, sessions)

        turn_counts[next_actor] += 1
        total_turns += 1

        # ── Verify the agent wrote a new block ──
        new_fields = get_latest_block_fields(workspace)
        new_next = new_fields.get("next", "").lower()
        new_status = new_fields.get("status", "").lower()

        if new_fields == fields:
            print(f"\n⚠  WARNING: handoff.md was not updated by {next_actor}. Check the agent output.")
            print("   You may need to manually inspect and re-run.")
            break

        print(f"  ✓ handoff.md updated → status={new_status}, next={new_next}")

        # Small pause to avoid hammering the API
        time.sleep(1)

    else:
        print(f"\n⚠  Reached max turns ({max_turns}). Stopping.")

    print(f"\n{'─'*60}")
    print(f"  Total turns:     {total_turns}")
    print(f"  Architect turns: {turn_counts['architect']}")
    print(f"  Engineer turns:  {turn_counts['engineer']}")
    print(f"{'─'*60}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Drive Architect + Engineer OpenCode sessions via handoff.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with defaults (uses opencode's configured model)
  python3 coordinator.py

  # Specify models
  python3 coordinator.py --architect-model anthropic/claude-sonnet-4-5 \\
                         --engineer-model anthropic/claude-sonnet-4-5

  # Reset sessions (forget prior context, start fresh)
  python3 coordinator.py --reset

  # Run from a different workspace
  python3 coordinator.py --workspace /path/to/my/project

  # Limit turns (useful for testing)
  python3 coordinator.py --max-turns 5
""",
    )
    parser.add_argument(
        "--workspace", type=Path, default=DEFAULT_WORKSPACE,
        help=f"Path to the coordination workspace (default: {DEFAULT_WORKSPACE})",
    )
    parser.add_argument(
        "--max-turns", type=int, default=DEFAULT_MAX_TURNS,
        help=f"Maximum number of agent turns (default: {DEFAULT_MAX_TURNS})",
    )
    parser.add_argument(
        "--architect-model", type=str, default=DEFAULT_ARCHITECT_MODEL,
        help="Model for architect agent (e.g. anthropic/claude-sonnet-4-5)",
    )
    parser.add_argument(
        "--engineer-model", type=str, default=DEFAULT_ENGINEER_MODEL,
        help="Model for engineer agent (e.g. anthropic/claude-sonnet-4-5)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Discard saved session IDs and start fresh sessions",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress streamed agent output (only show status lines)",
    )

    args = parser.parse_args()

    workspace = args.workspace.resolve()
    if not (workspace / "handoff.md").exists():
        print(f"❌  handoff.md not found in {workspace}")
        print("   Initialize the workspace first (see README.md).")
        sys.exit(1)

    run_coordinator(
        workspace=workspace,
        max_turns=args.max_turns,
        architect_model=args.architect_model,
        engineer_model=args.engineer_model,
        reset=args.reset,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
