# Workflow Guide

This document explains the multi-agent coordination loop, task lifecycle, and how to start, resume, or intervene in a session.

## Overview

The coordination workflow connects multiple AI agent sessions — by default **Architect**, **Developer**, and **QA Engineer** — that communicate exclusively through `handoff.md`. The human operator bootstraps sessions and can intervene at any time. The architect has final authority over all decisions.

```
Human
  │
  ▼
Architect ──assigns──▶ Developer ──review_required──▶ Architect
  ▲                                                       │
  │                                             routes to QA or approves
  │                                                       │
  │                                                       ▼
  └──────────────────────────────────────────── QA Engineer
                                                    │
                                          verdict → Architect
                                              │
                                    approve / challenge / rework
                                              │
                                    plan_complete ──▶ Human
```

## The Default Loop

1. **Coordinator starts** — reads `handoff.md`, identifies whose turn it is from the `NEXT:` field.

2. **Architect reads current state** — reads the latest valid `---HANDOFF---` block, `plan.md`, and `tasks.json`.

3. **Architect assigns a task** — selects the next unstarted task, writes a human-readable section, then appends a `---HANDOFF---` block with `STATUS: continue`, `NEXT: developer`, and explicit acceptance criteria.

4. **Developer reads the assignment** — confirms `NEXT: developer` in the latest block, reads the `TASK_ID`, acceptance criteria, constraints, and `FILES_TO_TOUCH`.

5. **Developer implements the task** — modifies only the files listed, stays within constraints, and runs local validation.

6. **Developer appends a handoff block** — writes a `---HANDOFF---` block with `STATUS: review_required`, `NEXT: architect`, listing `CHANGED_FILES` and `VALIDATION` results.

7. **Architect reviews** — decides whether to send to QA (`NEXT: qa_engineer`), approve directly, or request rework (`NEXT: developer`).

8. **QA Engineer validates** — runs tests, checks acceptance criteria, reports PASS/FAIL with evidence. Sets `NEXT: architect` — the verdict is a recommendation.

9. **Architect makes final call** — accepts QA verdict, challenges it (sends back to `qa_engineer`), or overrides it (sends to `developer` for rework).

10. **Repeat** until the architect writes `STATUS: plan_complete`.

## Task Lifecycle

Each task in `tasks.json` moves through the following states:

```
planned
  │
  ▼
ready_for_engineering
  │
  ▼
in_engineering ──────────────────────────┐
  │                                      │
  ▼                                      │
ready_for_architect_review               │
  │                                      │
  ├──approved──▶ done (terminal)         │
  │                                      │
  └──rework_requested ──────────────────►┘

Any non-terminal state ──▶ blocked
blocked ──▶ in_engineering | ready_for_engineering
```

### State Descriptions

| State | Who sets it | Meaning |
|---|---|---|
| `planned` | Initial | Task defined but not yet assigned |
| `ready_for_engineering` | Architect | Architect has signalled the task is next |
| `in_engineering` | Coordinator (auto) | Task has been routed to developer |
| `ready_for_architect_review` | Coordinator (auto) | Developer submitted `review_required` |
| `rework_requested` | Coordinator (auto) | Architect submitted `rework_required` |
| `done` | Coordinator (auto) | Architect approved the task |
| `blocked` | Either | Cannot proceed; human intervention needed |
| `needs_human` | Coordinator (auto) | Retry limit exceeded |

### Automatic Task Status Sync

The coordinator automatically updates `tasks.json` after each turn based on the handoff status:

| Handoff STATUS | Task transition |
|---|---|
| `continue` (to developer) | → `in_engineering` |
| `review_required` | → `ready_for_architect_review` |
| `rework_required` | → `rework_requested` |
| `approved` | → `done` |
| `blocked` | → `blocked` |
| `needs_human` | → `needs_human` |

### Lifecycle Enforcement

`TaskService.update_status()` enforces the transition map above. Invalid transitions raise `ValueError` naming both the current and attempted states. Only one task may be `in_engineering` at a time — attempting to start a second raises `ValueError`.

## Starting a Session

The coordinator handles session management automatically. Each agent gets a persistent OpenCode session that accumulates context across turns.

```bash
python3 coordinator.py --workspace /path/to/project
```

On first run, the coordinator:
1. Reads `handoff.md` to find the initial `NEXT:` target
2. Builds a prompt including the agent's role prompt, shared rules, and any project `AGENTS.md`
3. Calls `opencode run` with a new session
4. Saves the session ID for future turns

On subsequent runs, sessions are resumed automatically using saved IDs.

## Resuming an Interrupted Session

1. Open `handoff.md` and find the last `---HANDOFF---` block.
2. Check `NEXT` to determine which agent should act.
3. Check `STATUS` — if `blocked` or `needs_human`, resolve the issue first.
4. Re-run the coordinator.

The append-only invariant means no state is ever lost. The last valid block is always the authoritative source of truth.

## Human Intervention Points

The coordinator **stops** when any block contains `NEXT: human`. Common situations:

| Situation | STATUS in block | What to do |
|---|---|---|
| Architect declares completion | `plan_complete` | Review final output; no further agent action needed |
| Any agent is blocked | `blocked` | Resolve the blocker, then append a new directive block manually |
| Ambiguous requirement | `needs_human` | Clarify and append a new architect or instruction block |
| Retry limit exceeded | `needs_human` | Review the stuck task, fix root cause, re-run |

The human may also intervene proactively at any time by appending an instruction block to `handoff.md` before the next coordinator run.

## Handoff Write Retry

If an agent fails to update `handoff.md` after its turn (observed occasionally with LLMs), the coordinator automatically retries with a targeted "you must append a handoff block" message. This is configurable via `DEFAULT_HANDOFF_RETRIES` in `coordinator.py`.

## Parsing and Inspecting the Workflow

The `src/workflow.py` module exposes `get_workflow_state(path)` for programmatic inspection:

```python
from src.workflow import get_workflow_state

state = get_workflow_state("handoff.md")
# Returns:
# {
#   "valid": True,
#   "next_actor": "developer",       # plain string
#   "status": "continue",
#   "task_id": "task-005",
#   "is_complete": False,
#   "is_blocked": False,
#   "needs_human": False,
#   "errors": []
# }
```

Individual helpers are also available:

```python
from src.handoff_parser import extract_latest
from src.workflow import get_next_actor, is_plan_complete, is_human_escalation, is_blocked

with open("handoff.md") as f:
    content = f.read()

message, errors = extract_latest(content)
if message:
    print(get_next_actor(message))   # "developer" (plain string)
    print(is_plan_complete(message)) # False
```
