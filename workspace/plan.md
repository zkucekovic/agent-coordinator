# Agent Coordinator v2 — Implementation Plan

## Overview

This plan implements 17 requirements across 4 phases from SPECIFICATION.md. All changes are additive to the existing hexagonal architecture. Zero third-party dependencies (Python 3.10+ stdlib only).

## Task Ordering & Dependencies

```
Phase 1: Observability
  task-101  EventLog + turn observability (1.1, 1.2, 1.3)
  task-102  Log task transition failures (1.4)          ← depends on task-101 (type field)
  task-103  Enhanced workflow summary (1.5)

Phase 2: User Experience
  task-104  Display protocol abstraction (2.1)
  task-105  Workflow progress display (2.2)              ← depends on task-104
  task-106  Enhanced interrupt menu with context (2.3)   ← depends on task-104
  task-107  Guided human input builder (2.4)
  task-108  Dry-run mode (2.5)

Phase 3: Flexibility
  task-109  Configurable prompt sections per agent (3.1)
  task-110  Cycle detection (3.2)
  task-111  Per-agent turn timeout (3.3)
  task-112  Hot-reload agents.json (3.4)

Phase 4: Functionality
  task-113  Workspace init command (4.1)
  task-114  History and analysis command (4.2)
  task-115  Event hooks (4.3)

Final
  task-116  Final integration review & documentation
```

## Task Details

### task-101: EventLog Enhancements & Turn Observability

**Spec refs:** 1.1, 1.2, 1.3 — Grouped because they all modify `EventLog.append()` and the same coordinator loop section.

**Changes:**
- `event_log.py`: Add `response_text`, `prompt_file`, `prompt_hash`, `duration_seconds` to `append()`
- `cli.py` coordinator loop:
  - Accumulate output via `on_output` callback into a buffer
  - Capture `time.monotonic()` before/after runner call
  - Write prompt to `prompts_log/turn-{NNN}-{agent}.md`
  - Compute SHA-256 of prompt for `prompt_hash`
  - Pass all new fields to `event_log.append()`
- Unit tests for EventLog with new fields, prompt file writing

**Files:** `agent_coordinator/infrastructure/event_log.py`, `agent_coordinator/cli.py`, tests

### task-102: Log Task Transition Failures (1.4)

**Changes:**
- Add `"type"` field to all event records: `"turn"` for normal, `"warning"` for warnings
- In `_sync_task_status()`, catch `ValueError` and log via EventLog with warning details
- Pass `event_log` to `_sync_task_status()`

**Files:** `agent_coordinator/cli.py`, `agent_coordinator/infrastructure/event_log.py`, tests

### task-103: Enhanced Workflow Summary (1.5)

**Changes:**
- After existing `_print_summary()`, read tasks.json and print task status counts
- Calculate rework rates and total wall-clock duration from events
- Graceful degradation when data is absent

**Files:** `agent_coordinator/cli.py`, tests

### task-104: Display Protocol Abstraction (2.1)

**Changes:**
- Create `agent_coordinator/application/display.py` with `Display` Protocol
  - Methods: `start_run()`, `start_agent_turn()`, `update_output()`, `finish_agent_turn()`, `show_progress()`, `show_interrupt_menu()`, `close()`
- Create `PlainDisplay` implementing protocol with `print()` calls
- Refactor `cli.py` to type-hint against `Display`, not `TUIDisplay`
- Verify `TUIDisplay` satisfies protocol structurally

**Files:** new `agent_coordinator/application/display.py`, `agent_coordinator/cli.py`, tests

### task-105: Workflow Progress Display (2.2) — depends on task-104

**Changes:**
- Implement `show_progress()` in TUIDisplay and PlainDisplay
- Call after each turn: `Turn 7/30 | Tasks: 3/7 done | Reworks: 1`
- Graceful fallback when task_service is None

**Files:** `agent_coordinator/infrastructure/tui.py`, `agent_coordinator/cli.py`

### task-106: Enhanced Interrupt Menu with Context (2.3) — depends on task-104

**Changes:**
- Display context dashboard on Ctrl+C: turn, agent, backend, task ID, elapsed time, task progress
- Pass context from coordinator loop to interrupt handler

**Files:** `agent_coordinator/infrastructure/tui.py`, `agent_coordinator/cli.py`

### task-107: Guided Human Input Builder (2.4)

**Changes:**
- Add `g` option to human prompt menu
- Guided flow: STATUS → NEXT → SUMMARY selection
- Auto-populate ROLE, TASK_ID, TITLE; validate combinations
- Show block for confirmation before appending

**Files:** `agent_coordinator/infrastructure/human_prompt.py`, tests

### task-108: Dry-Run Mode (2.5)

**Changes:**
- Add `--dry-run` CLI argument
- Read handoff, determine next agent, build prompt, print to stdout, exit
- No file modifications

**Files:** `agent_coordinator/cli.py`, tests

### task-109: Configurable Prompt Sections Per Agent (3.1)

**Changes:**
- Add `"prompt"` key to agent config: `include_spec`, `include_plan`, `max_handoff_lines`, `extra_files`
- Modify `PromptBuilder.build()` to respect config
- Default behavior unchanged without config

**Files:** `agent_coordinator/application/prompt_builder.py`, tests

### task-110: Cycle Detection (3.2)

**Changes:**
- Track (agent, task_id) pairs in coordinator loop
- Detect 3+ consecutive same-pair without status change
- Warn, log, trigger interrupt menu; reset on continue

**Files:** `agent_coordinator/cli.py`, tests

### task-111: Per-Agent Turn Timeout (3.3)

**Changes:**
- Add `timeout_seconds` to retry policy and per-agent config (default: 300s)
- Kill runner subprocess on timeout, log event, trigger retry
- Manual runner exempt

**Files:** `agent_coordinator/cli.py`, runner implementations, tests

### task-112: Hot-Reload agents.json (3.4)

**Changes:**
- Move `load_config()` inside while loop
- Hash comparison, rebuild on change, retain previous on error

**Files:** `agent_coordinator/cli.py`, tests

### task-113: Workspace Init Command (4.1)

**Changes:**
- Add `init` subcommand: scaffold agents.json, handoff.md, prompts/
- Auto-detect backends, never overwrite, `--no-editor` flag

**Files:** new `agent_coordinator/helpers/init_workspace.py`, `agent_coordinator/cli.py`, tests

### task-114: History and Analysis Command (4.2)

**Changes:**
- Add `history` subcommand with timeline, --tasks, --stats modes
- Degrades gracefully without timing data

**Files:** new `agent_coordinator/helpers/history.py`, `agent_coordinator/cli.py`, tests

### task-115: Event Hooks (4.3)

**Changes:**
- Support `hooks/` directory: `on-turn-complete`, `on-task-done`, `on-workflow-complete`
- Async execution, 10s timeout, log failures as warnings

**Files:** new `agent_coordinator/infrastructure/hooks.py`, `agent_coordinator/cli.py`, tests

### task-116: Final Integration Review & Documentation

- Full test suite run
- Verify all 17 requirements against acceptance criteria
- Update README.md with new features
- Verify backward compatibility

## Testing Strategy

- Domain/application logic: unit tests (no I/O mocks)
- Phase 1: verify event record fields after append
- Phase 2: protocol conformance tests; manual visual tests for TUI
- Phase 3: unit tests for cycle detection, timeout, prompt config
- Phase 4: integration tests with sample data
