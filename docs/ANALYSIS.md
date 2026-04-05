# Codebase Analysis

This document covers three areas: problems that need fixing, functional improvements, and integration with existing agent harness infrastructure.

---

## 1. Problems and Fixes

### P1: agents.json is read twice on startup

`load_agent_config()` and `load_retry_policy()` each independently read and parse `agents.json`. This is a minor DRY violation now, but will compound if more config sections are added.

**Fix**: Create a single `load_config(workspace) -> dict` function that reads the file once and returns the full dict. Have `load_agent_config` and `load_retry_policy` accept the pre-loaded dict rather than a path.

### P2: Coordinator does not update tasks.json

The coordinator reads `tasks.json` for context (next ready task) but never writes status changes back. The agents are expected to update task statuses themselves, but they have no reliable way to do so — they operate through OpenCode, which may or may not have file-write access to `tasks.json`.

This means `tasks.json` drifts from reality after the first turn.

**Fix**: After each turn, the coordinator should read the new handoff block and apply the corresponding `TaskService` transition. For example: if a developer's block says `STATUS: review_required`, transition the task from `in_engineering` to `ready_for_architect_review`. This keeps the task registry in sync without relying on agents to manage it.

### P3: Handoff equality check is fragile

Line 138 of `coordinator.py` compares `new_message == message` to detect whether the agent updated `handoff.md`. This relies on Python dataclass `__eq__`, which compares all fields. If an agent happens to produce an identical block (same status, same summary, same everything), the coordinator would falsely conclude "not updated" and stop.

**Fix**: Compare the raw file content hash before and after the agent runs, or compare a monotonically increasing turn counter / timestamp in the handoff block.

### P4: No retry when an agent fails to write handoff.md

If an agent produces output but does not append a handoff block to the file (observed in integration tests with LLMs), the coordinator just warns and breaks. There is no retry attempt.

**Fix**: Add a configurable retry (1-2 attempts) where the coordinator re-sends a targeted "you must append a handoff block" message if the file was not updated after a turn.

### P5: Prompt path resolution is confusing

`PromptBuilder._load_role_prompt()` resolves `prompt_file` relative to the workspace path. But the default `agents.json` uses paths like `prompts/architect.md`, which exist relative to the coordinator's own directory, not the user's project workspace.

When pointing at a real project workspace, the coordinator looks for prompts inside that project directory. If they are not there, it falls back to a generic one-liner. The user's actual prompt files (in the coordinator repo's `prompts/` directory) are silently ignored.

**Fix**: Resolve prompt paths relative to the coordinator's installation directory by default. Allow `agents.json` to override with absolute paths or workspace-relative paths using a clear prefix convention (e.g. `workspace:prompts/custom.md` vs `prompts/architect.md`).

### P6: docs/protocol.md and docs/workflow.md are outdated

Both documents still reference a two-agent (architect + engineer) workflow. The system now supports three agents (architect, developer, qa_engineer) with arbitrary extension. Specific issues:
- `protocol.md` says `ROLE: <architect|engineer>`, `NEXT: <architect|engineer|human|none>`
- `workflow.md` describes a "two-agent coordination loop" and references "Engineer" throughout
- `workflow.md` references `TaskStore.update_status()` instead of `TaskService`
- The workflow diagram shows architect-engineer only

**Fix**: Update both documents to reflect the current three-agent setup and the extensible agent model.

### P7: Backwards-compat shims reference outdated API

`src/workflow.py` exports `get_next_actor()` which returns `message.next` — but the return type documentation in `docs/workflow.md` shows `NextActor.ENGINEER` (an enum). The actual return is a plain string now. Minor, but misleading to anyone reading the docs.

**Fix**: Update the code example in `docs/workflow.md` to show string returns.

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
