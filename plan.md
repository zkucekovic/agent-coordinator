# Implementation Plan — Coordination Workspace

## Overview

Build a two-agent (architect + engineer) coordination workspace in Python. The system provides structured handoff communication, task lifecycle management, workflow helpers, and supporting documentation.

## Phases

### Phase 1 — Scaffolding (task-001)
Create the repository skeleton: all required directories and placeholder files. This establishes the agreed-upon layout so all subsequent tasks have stable file paths to target.

### Phase 2 — Domain Models (task-002)
Define Python dataclasses/enums representing the core domain:
- `TaskStatus` enum: planned, in_engineering, review, approved, rework, complete
- `AgentRole` enum: architect, engineer, human
- `Task` dataclass: id, title, status, acceptance_criteria, constraints, files_to_touch, changed_files, validation, blockers
- `HandoffMessage` dataclass: role, status, next, task_id, title, summary, acceptance, constraints, files_to_touch, changed_files, validation, blockers, timestamp
- `ValidationResult` dataclass: valid (bool), errors (list[str])

### Phase 3 — Parser (task-003)
Implement `src/handoff_parser.py`:
- Parse raw handoff.md text into a list of `HandoffMessage` objects
- Extract the latest valid block
- Validate block structure and reject malformed entries (return ValidationResult with errors)

### Phase 4 — Task Store (task-004)
Implement `src/task_store.py`:
- Load/save tasks from/to `tasks.json`
- CRUD operations keyed by task id
- Status transition recording with timestamps

### Phase 5 — Lifecycle Rules (task-005)
Implement `src/task_store.py` lifecycle enforcement:
- Only allow valid status transitions (planned→in_engineering→review→approved/rework→complete)
- Enforce at-most-one task in `in_engineering` state at any time
- Raise descriptive errors on invalid transitions

### Phase 6 — Workflow Helpers (task-006)
Implement `src/handoff_parser.py` or a dedicated `src/workflow.py`:
- `derive_next_actor(message)` — infer who acts next from NEXT field
- `is_completion_guard_met(tasks)` — check if all tasks are complete
- `needs_human_escalation(message)` — detect NEXT: human or STATUS: needs_human

### Phase 7 — Tests (task-007)
Implement `tests/test_handoff_parser.py` and `tests/test_task_state.py`:
- Parser: valid block, malformed block, missing fields, multi-block extraction
- Task transitions: all valid paths, invalid transition rejection, concurrency guard
- End-to-end: parse a handoff, update task store, derive next actor

### Phase 8 — Documentation (task-008)
Finalize:
- `README.md` — project overview, setup, usage
- `docs/workflow.md` — workflow diagrams and explanation
- `docs/protocol.md` — handoff block format spec
- `prompts/architect.md`, `prompts/engineer.md`, `prompts/shared_rules.md`

### Phase 9 — Review & Completion (task-009)
Architect reviews all deliverables against acceptance criteria, runs tests, and declares `STATUS: plan_complete`.

## File Layout

```
coordination/
  README.md
  handoff.md
  plan.md
  tasks.json
  prompts/
    architect.md
    engineer.md
    shared_rules.md
  docs/
    protocol.md
    workflow.md
  src/
    __init__.py
    handoff_parser.py
    task_store.py
    models.py
  tests/
    __init__.py
    test_handoff_parser.py
    test_task_state.py
```

## Constraints

- Python 3.10+ only; standard library preferred (no external deps unless justified)
- All source files must be importable as a package (`src/`)
- `handoff.md` is append-only; no rewrites
- Tasks progress sequentially; no parallelism across phases
