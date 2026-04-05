# Codebase Analysis

This document covers three areas: problems that need fixing, functional improvements, and integration with existing agent harness infrastructure.

---

## 1. Problems and Fixes

All problems listed below have been fixed.

### P1: agents.json is read twice on startup — FIXED

`load_agent_config()` and `load_retry_policy()` each independently read and parse `agents.json`.

**Fix applied**: Created `load_config(workspace)` that reads the file once. Both `load_agent_config` and `load_retry_policy` now accept the pre-loaded dict.

### P2: Coordinator does not update tasks.json — FIXED

The coordinator reads `tasks.json` for context but never writes status changes back.

**Fix applied**: Added `_sync_task_status()` with a `_HANDOFF_TO_TASK_STATUS` mapping table. After each turn, the coordinator maps the handoff status to a `TaskService` transition and applies it. Invalid transitions are skipped silently.

### P3: Handoff equality check is fragile — FIXED

Line 138 of `coordinator.py` compared `new_message == message` using dataclass `__eq__`.

**Fix applied**: Replaced with SHA-256 content hash comparison (`_file_hash()`) of the raw handoff.md file before and after the agent runs.

### P4: No retry when an agent fails to write handoff.md — FIXED

If an agent produced output but did not append a handoff block, the coordinator just warned and broke.

**Fix applied**: Added a configurable retry loop (`DEFAULT_HANDOFF_RETRIES = 1`) that re-sends a targeted "you must append a handoff block" prompt via `_retry_prompt()`.

### P5: Prompt path resolution is confusing — FIXED

`PromptBuilder` resolved `prompt_file` relative to the workspace path, causing prompts to be silently ignored when pointing at a real project workspace.

**Fix applied**: `PromptBuilder` now accepts `coordinator_dir` and resolves prompt files relative to the coordinator's install directory first, falling back to the workspace. The coordinator passes `COORDINATOR_DIR` to the builder.

### P6: docs/protocol.md and docs/workflow.md are outdated — FIXED

Both documents referenced a two-agent (architect + engineer) workflow.

**Fix applied**: Rewrote both documents to reflect the three-agent setup (architect, developer, qa_engineer), the extensible agent model, automatic task status sync, and handoff write retry.

### P7: Backwards-compat shims reference outdated API — FIXED

Code examples in `docs/workflow.md` showed enum returns (`NextActor.ENGINEER`).

**Fix applied**: Updated all code examples to show string returns (`"developer"`).

---

## 2. Functional Improvements

### F1: Automatic task status synchronization

The coordinator should close the loop between `handoff.md` events and `tasks.json` state. After each turn, map the handoff status to a task transition:

| Handoff STATUS | Task transition |
|---|---|
| `continue` (NEXT: developer) | `planned` -> `ready_for_engineering` -> `in_engineering` |
| `review_required` | `in_engineering` -> `ready_for_architect_review` |
| `rework_required` | `ready_for_architect_review` -> `rework_requested` |
| `approved` | `ready_for_architect_review` -> `done` |

This makes `tasks.json` a reliable source of truth rather than a stale initial plan.

### F2: Workspace initialization command

There is no `init` or `setup` subcommand. Users must manually create `handoff.md`, `tasks.json`, and `agents.json`. A `python3 coordinator.py init /path/to/project` command that scaffolds these files with sensible defaults would reduce friction significantly.

### F3: Configuration validation on startup

The coordinator does not validate `agents.json` structure, `tasks.json` format, or `handoff.md` integrity before starting the loop. Bad config surfaces as a mid-run crash. Validate early and report clear errors.

### F4: Handoff block history query

The event log (`workflow_events.jsonl`) records metadata but not the actual handoff content. There is no way to replay or inspect the sequence of handoff blocks programmatically without parsing the entire `handoff.md` file.

Consider adding a `python3 coordinator.py history` subcommand that parses and displays all handoff blocks in a structured format (JSON or table).

### F5: Agent model configuration per role

`agents.json` supports `"model": null` but the README does not explain what models are available or how to set them. Document the model field and how it maps to `opencode run --model`.

### F6: Dry-run mode

Add a `--dry-run` flag that shows what the coordinator would do (which agent would run, what prompt would be sent) without actually invoking OpenCode. Useful for debugging prompt construction and routing logic.

### F7: Task assignment awareness

The coordinator passes `next_ready_task()` to the prompt builder, but only for context. The architect still has to manually assign tasks by writing the task ID in the handoff block. Consider making the coordinator suggest or auto-populate the next task ID when routing to the architect, reducing cognitive load on the LLM.

---

## 3. Reusing Existing Agent Harness Infrastructure

### What is agents.md?

GitHub Copilot (and tools like OpenCode, Codex, Claude Code) support repository-level agent configuration files — typically `AGENTS.md` or `agents.md` — that define ground rules, coding standards, architectural constraints, and behavioral policies for any AI agent working in that repository.

These files are already in use across the user's projects (observed in `epiphany/AGENTS.md`, `CheckFlow/agents.md`, and others). They encode:

- Spec-driven development rules
- Clean architecture constraints
- Testing requirements (coverage targets, TDD workflow)
- Commit and delivery policies
- Challenge policies (agent pushback behavior)
- Definition of done

### How this relates to agent-coordinator

The agent-coordinator already has analogous concepts:

| agents.md concept | agent-coordinator equivalent |
|---|---|
| Coding standards | `prompts/shared_rules.md` |
| Role definition | `prompts/architect.md`, `prompts/developer.md`, etc. |
| Testing requirements | Acceptance criteria in handoff blocks |
| Architecture rules | Embedded in agent prompts |
| Challenge policy | Architect final authority in `prompts/architect.md` |

### Integration approach

Rather than duplicating the content of `AGENTS.md` inside the coordinator's own prompt files, the coordinator should **load and inject the target project's `AGENTS.md` into agent prompts automatically**. This way:

1. The target project's existing rules are respected without manual copy-paste
2. The coordinator's own prompts focus on workflow protocol (how to hand off), not coding standards (how to code)
3. Different projects get different rules automatically

Implementation:

1. In `PromptBuilder.build()`, check if `workspace/AGENTS.md` or `workspace/agents.md` exists
2. If found, include its content in the first-turn preamble as "Project Rules"
3. Place it between the role prompt and shared rules, so the hierarchy is: role instructions > project rules > shared protocol rules
4. Document this in the README so users know their existing `AGENTS.md` is picked up automatically

### Skills and custom tools

Some AI agent frameworks support "skills" — reusable capability modules that agents can invoke. The coordinator does not currently have a skill system, but the extensible agent model provides a natural extension point:

- Each agent's prompt file could reference available skills (e.g., "you have access to a database migration skill")
- The coordinator could inject skill descriptions from a `skills/` directory in the workspace
- This is a future enhancement, not a current gap — the prompt-based system is flexible enough that skills can be described in natural language within agent prompts today

### Summary

The primary integration point is straightforward: auto-load `AGENTS.md` from the target workspace and inject it into agent prompts. This makes the coordinator respect project-level rules without configuration, and it works with the infrastructure users already have.
