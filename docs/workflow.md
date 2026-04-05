# Workflow Guide

This document explains the full two-agent coordination loop, task lifecycle, and how to start, resume, or intervene in a session.

## Overview

The coordination workflow pairs two AI agent sessions — **Architect** and **Engineer** — that communicate exclusively through `handoff.md`. The human operator bootstraps sessions and can intervene at any time.

```
Human
  │
  ▼
Architect ──assigns──▶ Engineer ──review_required──▶ Architect
  ▲                                                       │
  └───────────────────approved / rework_required──────────┘
                              │
                   plan_complete ──▶ Human
```

## The Default Loop (10 Steps)

1. **Human starts an architect session** — provides `prompts/architect.md`, `prompts/shared_rules.md`, and the full contents of `handoff.md`.

2. **Architect reads current state** — reads the latest valid `---HANDOFF---` block, `plan.md`, and `tasks.json`.

3. **Architect assigns a task** — selects the next unstarted task, writes a human-readable section, then appends a `---HANDOFF---` block with `STATUS: continue`, `NEXT: engineer`, and explicit acceptance criteria.

4. **Human starts an engineer session** — provides `prompts/developer.md`, `prompts/shared_rules.md`, and the full contents of `handoff.md`.

5. **Engineer reads the assignment** — confirms `NEXT: engineer` in the latest block, reads the `TASK_ID`, acceptance criteria, constraints, and `FILES_TO_TOUCH`.

6. **Engineer implements the task** — modifies only the files listed, stays within constraints, and runs local validation.

7. **Engineer appends a handoff block** — writes a human-readable summary then a `---HANDOFF---` block with `STATUS: review_required`, `NEXT: architect`, listing `CHANGED_FILES` and `VALIDATION` results.

8. **Human starts an architect session** — provides the same prompts plus the updated `handoff.md`.

9. **Architect reviews the output** — checks each acceptance criterion against the engineer's report and the actual files. Appends either:
   - `STATUS: approved` → marks task done in `tasks.json`, assigns next task, or declares completion.
   - `STATUS: rework_required` → describes exactly what to fix; engineer receives the task again.

10. **Repeat steps 4–9** until the architect writes `STATUS: plan_complete`.

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
| `in_engineering` | Engineer | Engineer has accepted and started work |
| `ready_for_architect_review` | Engineer | Implementation complete; awaiting review |
| `rework_requested` | Architect | Review rejected; engineer must fix and resubmit |
| `done` | Architect | Approved and complete (terminal) |
| `blocked` | Either | Cannot proceed; human intervention needed |

### Lifecycle Enforcement

`TaskStore.update_status()` enforces the transition map above. Invalid transitions raise `ValueError` naming both the current and attempted states. Only one task may be `in_engineering` at a time — attempting to start a second raises `ValueError`.

## Starting a New Session

### Architect session

```
System prompt: contents of prompts/architect.md
User message:  contents of prompts/shared_rules.md + full handoff.md
```

The architect reads the file, decides what to do, and appends its block.

### Engineer session

```
System prompt: contents of prompts/developer.md
User message:  contents of prompts/shared_rules.md + full handoff.md
```

The engineer reads the latest block, confirms `NEXT: engineer`, and proceeds.

## Resuming an Interrupted Session

1. Open `handoff.md` and find the last `---HANDOFF---` block.
2. Check `NEXT` to determine which agent should act.
3. Check `STATUS` — if `blocked` or `needs_human`, resolve the issue first.
4. Start the appropriate agent session with the current `handoff.md`.

The append-only invariant means no state is ever lost. The last valid block is always the authoritative source of truth.

## Human Intervention Points

The human operator **must** intervene when any block contains `NEXT: human`. Common situations:

| Situation | STATUS in block | What to do |
|---|---|---|
| Architect declares completion | `plan_complete` | Review final output; no further agent action needed |
| Either agent is blocked | `blocked` | Resolve the blocker, then append a new directive block manually |
| Ambiguous requirement | `needs_human` | Clarify and append a new architect or instruction block |
| Scope creep detected | `needs_human` | Correct the scope, re-assign the task |

The human may also intervene proactively at any time by appending an instruction block to `handoff.md` before starting the next agent session.

## Parsing and Inspecting the Workflow

The `src/workflow.py` module exposes `get_workflow_state(path)` for programmatic inspection:

```python
from src.workflow import get_workflow_state

state = get_workflow_state("handoff.md")
# Returns:
# {
#   "valid": True,
#   "next_actor": "engineer",
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
    print(get_next_actor(message))   # NextActor.ENGINEER
    print(is_plan_complete(message)) # False
```
