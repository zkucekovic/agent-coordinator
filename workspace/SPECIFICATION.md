# Agent Coordinator v2 Specification

## Overview

This specification defines improvements to the Agent Coordinator across four areas: observability, user experience, flexibility, and functionality. Each requirement includes acceptance criteria and constraints. The existing architecture (hexagonal layers, handoff protocol, backend agnosticism) is preserved — these are additive improvements, not a rewrite.

All changes maintain the zero-third-party-dependency constraint unless explicitly noted. Python 3.10+ stdlib only.

---

## Phase 1: Observability

### 1.1 Persist Agent Output Per Turn

**Problem**: Agent responses are displayed in the TUI and then discarded. When debugging misbehavior, there is no record of what the agent said or why it made a decision.

**Requirement**: Save the full text output from each agent turn alongside the event metadata.

**Implementation**:
- Add a `response_text` field to each record in `workflow_events.jsonl`
- The text is the complete stdout captured from the runner's `on_output` callback
- Accumulate output chunks in the coordinator loop and pass the full text to `EventLog.append()`
- Add an `extra` field `"prompt_hash"` — the SHA-256 of the prompt sent, so prompts can be correlated without storing them inline

**Acceptance**:
- After a workflow run, every event in `workflow_events.jsonl` includes a `response_text` field containing the agent's full output
- The field is present even when the output is empty (empty string, not omitted)
- Existing event fields (`ts`, `turn`, `agent`, `task_id`, `status_before`, `status_after`, `session_id`) are unchanged

**Constraints**:
- Do not break the JSONL format — each record must be a single line of valid JSON
- Long responses must not be truncated (the file is an audit trail)
- Escape newlines within `response_text` as `\n` in the JSON serialization (standard `json.dumps` handles this)

### 1.2 Persist Prompts Per Turn

**Problem**: The assembled prompt (role instructions + project rules + spec + handoff content) is never saved. When an agent misbehaves, you cannot determine whether the prompt was wrong or the agent ignored correct instructions.

**Requirement**: Save the full prompt sent to each agent, per turn.

**Implementation**:
- Write per-turn prompt files to a `prompts_log/` directory inside the workspace: `prompts_log/turn-{NNN}-{agent}.md`
- Create the directory automatically on first write
- Add the file path to the event record as `"prompt_file"` field

**Acceptance**:
- After a workflow run, `prompts_log/` contains one `.md` file per turn
- Each file contains the exact prompt string that was passed to the runner
- The event record in `workflow_events.jsonl` includes `"prompt_file": "prompts_log/turn-001-architect.md"`

**Constraints**:
- Prompt files are plain text, not JSON
- Numbering is zero-padded to 3 digits (`turn-001`, `turn-002`)
- Add `prompts_log/` to the default `.gitignore` recommendation in docs

### 1.3 Add Timing Data to Events

**Problem**: No record of how long each turn takes. Cannot identify which agents or backends are bottlenecks.

**Requirement**: Record wall-clock duration for each agent turn.

**Implementation**:
- Capture `time.monotonic()` before and after the runner call in the coordinator loop
- Add `duration_seconds` (float, 2 decimal places) to each event record

**Acceptance**:
- Every event record includes `"duration_seconds": <float>`
- Duration includes only the runner execution time, not TUI rendering or post-processing
- Timing is accurate to within 0.1 seconds

**Constraints**:
- Use `time.monotonic()`, not `time.time()` (immune to clock adjustments)

### 1.4 Log Task State Transition Failures

**Problem**: In `cli.py` line ~194, `TaskService.update_status()` failures are caught with `except ValueError: pass`. Task state and handoff state can silently diverge.

**Requirement**: Log transition failures as warning events instead of swallowing them silently.

**Implementation**:
- In `_sync_task_status()`, catch `ValueError` and log a warning event to `EventLog` with `"level": "warning"` and `"error"` containing the exception message
- Also print the warning when `--verbose` is active (current behavior preserved)

**Acceptance**:
- When a task transition fails, `workflow_events.jsonl` contains a record with `"level": "warning"` and the transition error message
- The coordinator does not exit or crash on transition failures (current behavior preserved)
- The warning event includes `turn`, `agent`, `task_id`, and the attempted transition (from → to)

**Constraints**:
- Warning events use the same JSONL format as turn events
- Add a `"type"` field to distinguish: `"type": "turn"` for normal events, `"type": "warning"` for warnings

### 1.5 Workflow Summary on Completion

**Problem**: When the workflow finishes, the summary shows only turn counts per agent. No visibility into task outcomes, rework rates, or total duration.

**Requirement**: Print an enhanced summary on workflow completion.

**Implementation**:
- Read `tasks.json` (if present) and print task statuses: done, blocked, in-progress
- Calculate total workflow duration from first to last event timestamp
- Calculate rework rate: total rework cycles / total tasks
- Print the summary in a structured format after the existing `_print_summary()`

**Acceptance**:
- On workflow completion, the summary includes:
  - Total turns and per-agent breakdown (existing)
  - Task summary: N done, N in-progress, N blocked (if tasks.json exists)
  - Total rework cycles across all tasks
  - Total wall-clock duration (from first turn start to last turn end)
- If tasks.json does not exist, only the turn summary is shown (graceful degradation)

**Constraints**:
- Do not change the existing `_print_summary()` function signature
- Add new summary output after the existing output

---

## Phase 2: User Experience

### 2.1 Display Protocol — Abstract the TUI Interface

**Problem**: The coordinator loop in `cli.py` is coupled to `TUIDisplay`. Swapping display implementations (plain text, Rich, Textual, JSON) requires editing the coordinator loop.

**Requirement**: Define a `Display` protocol that the coordinator loop depends on, instead of the concrete `TUIDisplay` class.

**Implementation**:
- Create `agent_coordinator/application/display.py` with a `Display` `Protocol` class
- Methods: `start_turn()`, `update_output()`, `finish_turn()`, `show_progress()`, `show_interrupt_menu()`
- `TUIDisplay` implements this protocol (structural typing — no inheritance required)
- The coordinator loop accepts a `Display` instance

**Acceptance**:
- `cli.py` imports and type-hints against `Display`, not `TUIDisplay`
- `TUIDisplay` satisfies the `Display` protocol without changes to its public API
- A new `PlainDisplay` class exists for non-TTY / `--quiet` mode that implements `Display` with simple `print()` calls
- All existing tests pass without modification

**Constraints**:
- Use `typing.Protocol` (available in Python 3.10+)
- Do not introduce abstract base classes — protocol is structural
- Do not change `TUIDisplay`'s class hierarchy

### 2.2 Workflow Progress in Status Bar

**Problem**: No indication of overall workflow progress. After 15 turns, the user does not know how close the workflow is to completion.

**Requirement**: Show task-level progress and turn counter in the TUI.

**Implementation**:
- Add a `show_progress()` method to `TUIDisplay` (already defined in Display protocol)
- Call it after each turn with: tasks done/total, current turn/max turns, current task rework count
- Display format in the turn header: `Turn 7/30 | Tasks: 3/7 done | Reworks: 1`

**Acceptance**:
- The turn header includes turn counter, task progress (when tasks.json exists), and rework count
- When tasks.json does not exist, only the turn counter is shown
- Progress updates after each turn completes

**Constraints**:
- Do not change the existing status bar layout — add progress to the turn header section
- Graceful degradation: if task_service is None, show only turn counter

### 2.3 Enhanced Interrupt Menu with Context

**Problem**: The Ctrl+C interrupt menu shows no context about the current workflow state. The user must inspect files manually to understand where the workflow is.

**Requirement**: Show a status dashboard when Ctrl+C is pressed, before the menu options.

**Implementation**:
- When the interrupt menu is shown, display:
  - Current turn number and max turns
  - Active agent and backend
  - Current task ID and status
  - Elapsed time since workflow start
  - Task progress summary (N done / N total)
- Pass this context from the coordinator loop to `handle_interrupt()`

**Acceptance**:
- Pressing Ctrl+C shows a context block above the menu options
- All context fields are populated from current coordinator state
- If task_service is unavailable, task-related fields are omitted
- Menu options remain unchanged: c, r, e, m, i, q

**Constraints**:
- Do not change the menu option keys or behavior
- Context display uses the same color scheme as the existing TUI

### 2.4 Guided Human Input Builder

**Problem**: When `NEXT: human` triggers, the user must either type a raw handoff block or edit the full `handoff.md`. Both are error-prone.

**Requirement**: Provide a guided flow that constructs a valid handoff block from user inputs.

**Implementation**:
- Add a new option `g` (guided) to the human prompt menu
- The guided flow prompts for:
  1. STATUS: choice from valid values (continue, rework_required, approved, blocked, needs_human)
  2. NEXT: choice from configured agent names + "human" + "none"
  3. SUMMARY: free-text (opened in $EDITOR if multiline)
- Auto-populate: ROLE as "human", TASK_ID from the current block, TITLE from the current block
- Generate the complete `---HANDOFF---` block and append to `handoff.md`
- Show the generated block for confirmation before appending

**Acceptance**:
- The guided flow produces a valid handoff block that passes `HandoffParser` validation
- ROLE is always "human"
- TASK_ID and TITLE are carried forward from the previous block
- The user can abort at any step without modifying `handoff.md`
- The generated block is shown for review before being appended

**Constraints**:
- The existing "respond" (`r`) and "edit" (`e`) options remain available as alternatives
- The guided flow uses `enhanced_input` for readline support
- Validation: reject if STATUS and NEXT combination is logically invalid (e.g., `STATUS: approved, NEXT: developer`)

### 2.5 Dry-Run Mode

**Problem**: Cannot preview what prompt will be sent to an agent before executing. Makes prompt debugging difficult.

**Requirement**: A `--dry-run` flag that builds and prints the next turn's prompt without executing.

**Implementation**:
- Add `--dry-run` argument to CLI
- When active: read handoff, determine next agent, build prompt, print to stdout, exit
- Do not invoke any runner, modify any files, or log any events

**Acceptance**:
- `agent-coordinator --workspace ./project --dry-run` prints the full prompt and exits with code 0
- The prompt printed is identical to what would be sent to the runner
- No files are modified (handoff.md, tasks.json, workflow_events.jsonl, sessions)
- If the workflow would be terminal (plan_complete, blocked), print the stop reason instead

**Constraints**:
- Dry-run always exits after printing — it does not enter the loop
- Output goes to stdout with no TUI formatting (suitable for piping)

---

## Phase 3: Flexibility

### 3.1 Configurable Prompt Sections Per Agent

**Problem**: `PromptBuilder` uses a fixed template: role → rules → spec → plan → shared_rules → handoff. All agents get all sections. After 20 turns, the handoff content alone can be thousands of tokens.

**Requirement**: Allow per-agent configuration of which prompt sections are included and how handoff content is truncated.

**Implementation**:
- Add an optional `"prompt"` key to agent config in `agents.json`:
  ```json
  "developer": {
    "prompt": {
      "include_spec": false,
      "include_plan": false,
      "max_handoff_lines": 150,
      "extra_files": ["CODING_STANDARDS.md"]
    }
  }
  ```
- `include_spec` (default: true on first turn): whether to inject SPECIFICATION.md
- `include_plan` (default: true on first turn): whether to inject plan.md
- `max_handoff_lines` (default: 0 = no limit): truncate handoff.md to last N lines
- `extra_files` (default: []): additional workspace files to inject as named sections
- `PromptBuilder.build()` reads these from `agent_cfg` and adjusts accordingly

**Acceptance**:
- An agent with `"include_spec": false` does not receive SPECIFICATION.md content in any turn
- An agent with `"max_handoff_lines": 100` receives only the last 100 lines of handoff.md
- An agent with `"extra_files": ["API.md"]` receives the content of `workspace/API.md` as a section
- Default behavior (no `"prompt"` key) is identical to current behavior
- Existing tests pass without modification

**Constraints**:
- Do not change the prompt injection order — only control inclusion/exclusion
- `extra_files` paths are relative to the workspace root
- If an extra file does not exist, skip it silently (do not error)
- `max_handoff_lines` truncates from the beginning, keeping the most recent content

### 3.2 Cycle Detection

**Problem**: If agents route in a loop (A→B→A→B), the workflow burns tokens until `--max-turns` is exhausted. There is no warning.

**Requirement**: Detect routing cycles and warn the user.

**Implementation**:
- Track the last N routing decisions in the coordinator loop (agent name + task_id pairs)
- Define a cycle as: the same (agent, task_id) pair appearing 3+ times consecutively without a status change to `approved`, `done`, or `plan_complete`
- When a cycle is detected: print a warning, log a warning event, and trigger the interrupt menu

**Acceptance**:
- A workflow that loops A→B→A→B→A→B (3 cycles of A→B on the same task) triggers a warning
- The warning includes the cycling agents and the task ID
- The interrupt menu is shown so the user can continue, retry, or quit
- If the user chooses to continue, the cycle counter resets
- Cycle detection does not trigger for legitimate review loops (architect→developer→architect) where the task status changes between cycles

**Constraints**:
- Do not prevent the cycle from running — only warn and offer intervention
- Cycle detection is based on consecutive same-(agent, task_id) patterns, not global history
- Status changes (e.g., continue → rework_required → continue) reset the cycle counter for that task

### 3.3 Per-Agent Turn Timeout

**Problem**: If a backend hangs (network issue, rate limit, unresponsive process), the coordinator waits indefinitely.

**Requirement**: Configurable timeout for agent execution.

**Implementation**:
- Add `"timeout_seconds"` to the retry policy in `agents.json` (applies to all agents)
- Add optional `"timeout_seconds"` per agent in `agents.json` (overrides global)
- Default: 300 seconds (5 minutes)
- When a turn exceeds the timeout: kill the runner subprocess, log a timeout event, treat as a failed handoff update, and trigger the existing retry logic

**Acceptance**:
- A backend that takes longer than `timeout_seconds` is terminated
- The event log records a timeout event with `"type": "timeout"` and `"duration_seconds"`
- The retry logic runs after a timeout (same as when handoff.md is not updated)
- The default timeout of 300 seconds applies when no explicit config is set
- Per-agent timeout overrides the global timeout

**Constraints**:
- Timeout applies to the runner subprocess only, not to TUI rendering or post-processing
- Use `subprocess.Popen` with `communicate(timeout=N)` for subprocess-based runners
- For the manual runner, timeout does not apply (human input has no time limit)

### 3.4 Hot-Reload agents.json

**Problem**: Changing agent configuration mid-workflow requires stopping and restarting the coordinator.

**Requirement**: Re-read `agents.json` at the start of each turn.

**Implementation**:
- Move `load_config()` call inside the while loop, before each turn
- Compare config hash with previous iteration; if changed, rebuild agent config and invalidate runner cache
- Print a notice when config changes are detected

**Acceptance**:
- Editing `agents.json` during a workflow run takes effect on the next turn
- Changing an agent's backend mid-workflow creates a new runner (old sessions preserved)
- Changing the retry policy mid-workflow takes effect immediately
- A notice is printed when config reload is detected
- If `agents.json` has a syntax error, the previous valid config is retained and a warning is printed

**Constraints**:
- Session IDs are not invalidated on config change (only runner instances)
- Config reload overhead is negligible (<1ms) compared to LLM turn time
- Do not re-read on every sub-operation — only at the start of each turn

---

## Phase 4: Functionality

### 4.1 Workspace Initialization Command

**Problem**: Every new project requires manually creating `handoff.md`, `agents.json`, and prompt files. The README documents the format but there is no scaffolding tool.

**Requirement**: An `agent-coordinator init` command that creates a workspace with all necessary files.

**Implementation**:
- Add an `init` subcommand (or `--init` flag) to the CLI
- Creates in the target workspace:
  - `agents.json` with default config (auto-detect available backends)
  - `handoff.md` with the standard initial architect block (existing `_create_initial_handoff()` logic)
  - `prompts/` directory with copies of default prompt files from the package
- If any file already exists, skip it and print a notice (never overwrite)
- After creation, open `SPECIFICATION.md` in `$EDITOR` if the file does not exist (optional, skip if `--no-editor`)

**Acceptance**:
- `agent-coordinator init --workspace ./my-project` creates a valid workspace
- Running `agent-coordinator --workspace ./my-project` immediately after `init` starts a working workflow
- Existing files are never overwritten
- `--no-editor` skips the editor step
- Backend auto-detection: check PATH for `gh`, `claude`, `opencode` and set `default_backend` accordingly

**Constraints**:
- Init does not start a workflow — it only scaffolds files
- The created `agents.json` uses the same schema as the existing default
- Prompt files are copied from the installed package, not symlinked

### 4.2 Workflow History and Analysis Command

**Problem**: `workflow_events.jsonl` is a complete audit trail but there are no tools to analyze it. Debugging requires manual `jq` or Python scripts.

**Requirement**: An `agent-coordinator history` command that reads the event log and prints structured summaries.

**Implementation**:
- Add a `history` subcommand to the CLI with sub-modes:
  - `agent-coordinator history --workspace ./project` (default): chronological timeline
  - `agent-coordinator history --workspace ./project --tasks`: per-task lifecycle summary
  - `agent-coordinator history --workspace ./project --stats`: aggregate statistics

- **Timeline mode** (default): Print each turn as a one-line summary:
  ```
  Turn  1 | architect   | task-000 | continue → continue     | 12.3s
  Turn  2 | developer   | task-001 | continue → review_req   | 45.7s
  Turn  3 | qa_engineer | task-001 | continue → continue     | 23.1s
  ```

- **Tasks mode**: Per-task lifecycle:
  ```
  task-001: Implement login endpoint
    planned → in_engineering → review → rework (×1) → review → done
    Turns: 4 | Duration: 3m 12s | Reworks: 1

  task-002: Add input validation
    planned → in_engineering → review → done
    Turns: 3 | Duration: 2m 05s | Reworks: 0
  ```

- **Stats mode**: Aggregate metrics:
  ```
  Total turns:     15
  Total duration:  12m 34s
  Tasks completed: 5/7
  Rework rate:     28% (4 reworks across 5 tasks)
  Avg turn time:   50.3s
  Agent breakdown:
    architect:   6 turns, avg 15.2s
    developer:   5 turns, avg 78.4s
    qa_engineer: 4 turns, avg 34.1s
  ```

**Acceptance**:
- All three modes produce correct output from a `workflow_events.jsonl` file
- Timeline mode works with the existing event format (no new fields required)
- Tasks mode cross-references `workflow_events.jsonl` with `tasks.json` when available
- Stats mode calculates duration from `duration_seconds` field (added in 1.3); if absent, shows "N/A"
- Empty event log produces a "No events found" message, not an error

**Constraints**:
- Read-only: never modifies any files
- Output goes to stdout in plain text (no TUI, no colors unless `--color` is passed)
- Depends on Phase 1 features (1.3 for timing data) for full functionality, but degrades gracefully without them

### 4.3 Event Hooks

**Problem**: There is no way to run custom logic when workflow events occur (turn complete, task done, workflow finished) without modifying `cli.py`.

**Requirement**: Support optional event hook scripts that run on specific workflow events.

**Implementation**:
- Check for a `hooks/` directory in the workspace
- Supported hook scripts (executable files):
  - `hooks/on-turn-complete` — called after each successful turn
  - `hooks/on-task-done` — called when a task transitions to done
  - `hooks/on-workflow-complete` — called when the workflow finishes
- Each hook receives event data as JSON on stdin
- Hooks run asynchronously (non-blocking) with a 10-second timeout
- Hook failures are logged as warnings but never stop the workflow

**Acceptance**:
- A `hooks/on-turn-complete` script in the workspace is called after each turn
- The script receives the event record (same as `workflow_events.jsonl` entry) on stdin
- Hook scripts that do not exist are silently skipped
- Hook scripts that fail (non-zero exit, timeout) produce a warning in the event log
- Hook scripts that hang beyond 10 seconds are killed

**Constraints**:
- Hooks are optional — if no `hooks/` directory exists, no overhead is incurred
- Hook scripts must be executable (`chmod +x`)
- The coordinator does not wait for hooks to complete before proceeding to the next turn
- Hooks receive the workspace path as the `WORKSPACE` environment variable

---

## Already Implemented

The following features were built prior to this specification and are complete. Do not re-implement them.

### ✅ Import Command (`--import FILE`)

**Status**: Done — `agent_coordinator/helpers/import_plan.py`, wired into `cli.py` as `--import`.

The `--import FILE` flag on `agent-coordinator` imports a specification or implementation plan into a workspace. It auto-detects whether the file is a spec or a plan, parses tasks from plan headings into `tasks.json`, and creates a tailored `handoff.md` pointing the architect at the first task.

```bash
agent-coordinator --import SPECIFICATION.md --workspace ./my-project
agent-coordinator --import plan.md --workspace ./my-project --type plan --force
```

Supporting flags already on `agent-coordinator`: `--type spec|plan`, `--force`, `--no-handoff`, `--no-tasks`.

---



These are explicitly excluded from this specification:

- **Parallel agent execution**: Sequential turn-based execution is a core design decision for auditability. Not changing.
- **TUI framework migration** (Rich/Textual): The Display protocol (2.1) enables this in the future, but the actual migration is separate work.
- **Network-based communication**: Local filesystem protocol only.
- **Authentication/authorization**: Local trust model preserved.
- **Built-in runner refactoring**: Existing built-in runners (Copilot, Claude, OpenCode) keep their current implementations. GenericRunner handles new backends.
- **Plugin registration system**: The runner factory stays in `cli.py`. Entry-points-based discovery is future work.

---

## Implementation Notes

### Dependency on phases

Phases are designed to be implemented in order, but most requirements within a phase are independent.

Cross-phase dependencies:
- 2.2 (progress display) benefits from task_service data but works without it
- 4.2 (history command) benefits from 1.3 (timing data) but degrades gracefully
- 2.1 (Display protocol) should be done before 2.2 and 2.3

### Testing strategy

- All new domain/application logic must have unit tests
- Observability changes (Phase 1) are testable by reading `workflow_events.jsonl` after a run
- TUI changes (Phase 2) should have unit tests for logic and manual visual tests for rendering
- CLI commands (Phase 4) should have integration tests that run against sample event logs

### Files likely to change

| Requirement | Primary files |
|---|---|
| 1.1 Output persistence | `cli.py`, `event_log.py` |
| 1.2 Prompt persistence | `cli.py`, `event_log.py` |
| 1.3 Timing data | `cli.py`, `event_log.py` |
| 1.4 Transition warnings | `cli.py`, `event_log.py` |
| 1.5 Enhanced summary | `cli.py` |
| 2.1 Display protocol | new `application/display.py`, `cli.py`, `tui.py` |
| 2.2 Progress display | `tui.py`, `cli.py` |
| 2.3 Interrupt context | `tui.py`, `cli.py` |
| 2.4 Guided human input | `human_prompt.py` |
| 2.5 Dry-run mode | `cli.py` |
| 3.1 Prompt sections | `prompt_builder.py`, agents.json schema |
| 3.2 Cycle detection | `cli.py`, new logic in coordinator loop |
| 3.3 Turn timeout | `cli.py`, runner implementations |
| 3.4 Hot-reload config | `cli.py` |
| 4.1 Init command | `cli.py`, new init module |
| 4.2 History command | new `history.py` module |
| 4.3 Event hooks | `cli.py`, new `hooks.py` module |
