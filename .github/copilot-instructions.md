# Copilot Instructions

## Build, Test, and Run

```bash
# Install from source (stdlib only — no third-party dependencies)
pip install -e .

# Run unit tests (188 tests, no I/O, no API calls)
python3 -m unittest discover tests/ -v

# Run a single test file
python3 -m unittest tests/test_handoff_parser.py -v

# Run a single test case
python3 -m unittest tests.test_handoff_parser.TestExtractLatest.test_single_block -v

# Integration tests (require real API tokens)
RUN_INTEGRATION_TESTS=1 python3 -m unittest discover tests/integration/ -v

# Run the coordinator
agent-coordinator --workspace ./workspace --max-turns 20
```

## Architecture

This project follows **hexagonal architecture** with three layers. The installable package is `agent_coordinator/` — **do not confuse with `src/`**, which is an older parallel copy and is not imported by the active code.

```
agent_coordinator/
  cli.py                # Entry point and orchestration loop
  domain/               # Pure data models, state machine, retry policy — no I/O
  application/          # Router, PromptBuilder, TaskService, AgentRunner interface
  infrastructure/       # Runners (copilot, claude, opencode, manual, generic), file I/O, TUI
  handoff_parser.py     # Regex-based parser for handoff blocks
  prompts/              # Agent prompt templates (architect.md, developer.md, qa_engineer.md, shared_rules.md)
```

**Data flow per turn:**
1. `cli.py` reads the latest `---HANDOFF---` block from `handoff.md`
2. `WorkflowRouter` reads `NEXT:` to decide which agent runs
3. `PromptBuilder` assembles the prompt: role instructions → AGENTS.md → SPECIFICATION.md/plan.md → shared_rules.md → handoff.md
4. An `AgentRunner` dispatches to the backend CLI subprocess
5. `cli.py` verifies `handoff.md` was updated; retries with a reminder if not
6. `TaskService` syncs `tasks.json` based on `STATUS:`
7. Event appended to `workflow_events.jsonl`

## Key Conventions

### Handoff protocol
`handoff.md` is **append-only**. Every agent turn appends a block; nothing is edited or deleted. The structured block (between `---HANDOFF---` and `---END---`) is authoritative over any surrounding prose.

Required scalar fields: `ROLE`, `STATUS`, `NEXT`, `TASK_ID`, `TITLE`, `SUMMARY`  
List fields: `ACCEPTANCE`, `CONSTRAINTS`, `FILES_TO_TOUCH`, `CHANGED_FILES`, `VALIDATION`, `BLOCKERS`

### Adding a new backend runner
Implement `AgentRunner` (in `agent_coordinator/application/runner.py`) and register it in the factory in `cli.py`. Reference it in `agents.json` as `"backend": "my_runner"`. For fully configurable CLI tools, use `GenericRunner` with a `backend_config` block instead of writing Python.

### Routing is data-driven
Agents route to each other by writing `NEXT: <role-name>` in their handoff block. No code changes are needed to add a new agent role — create a prompt file, add the agent to `agents.json`, and update other agents' prompts to route to it.

### Prompt injection order (first turn only)
Role prompt → AGENTS.md (project rules) → SPECIFICATION.md / plan.md → shared_rules.md → handoff.md content. On subsequent turns, only the handoff content is re-injected.

### Domain layer stays pure
`agent_coordinator/domain/` has zero I/O and zero external dependencies. All file access goes through `infrastructure/`, all orchestration through `application/`. Tests for domain logic use no mocks.

### Session persistence
Agent session IDs are stored in `<workspace>/.coordinator_sessions.json` (gitignored). Re-running the coordinator resumes context. Use `--reset` to clear sessions.

### `src/` directory
This directory mirrors parts of `agent_coordinator/` but is not used by the installed package. It may be removed in a future cleanup.
