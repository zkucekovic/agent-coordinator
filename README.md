# Agent Coordinator

A tool-agnostic protocol and coordinator for multi-agent AI workflows. Agents communicate through structured, append-only handoff files. The coordinator drives the loop — routing turns, enforcing task lifecycle rules, logging events — while remaining independent of any specific AI backend.

Works with OpenCode, Claude Code, or a human operator. Mix backends freely: use Claude for architecture, OpenCode for implementation, and a human for final review — all in the same workflow.

## Why this exists

Most multi-agent systems are locked to a single provider. This project separates the **workflow protocol** (how agents communicate and hand off work) from the **execution backend** (what runs the agents). The protocol is the product:

- A structured, append-only `handoff.md` file that any tool can read and write
- A task lifecycle state machine with validated transitions
- An authority hierarchy where the architect has final say
- A full audit trail in `workflow_events.jsonl`

The coordinator is a thin loop that reads the protocol and dispatches to whichever backend each agent is configured to use.

## Supported backends

| Backend | CLI | Config value | Status |
|---|---|---|---|
| OpenCode | `opencode run` | `"opencode"` | Tested |
| Claude Code | `claude --print` | `"claude"` | Implemented |
| Manual (human) | stdin prompt | `"manual"` | Implemented |

Each agent can use a different backend. Set it per-agent in `agents.json`:

```json
{
  "default_backend": "opencode",
  "agents": {
    "architect": { "backend": "opencode", "model": "claude-sonnet-4" },
    "developer": { "backend": "claude" },
    "qa_engineer": { "backend": "manual" }
  }
}
```

## How it works

Each agent turn follows the same pattern regardless of backend:

1. The coordinator reads `handoff.md` and identifies whose turn it is (`NEXT:` field)
2. It builds a prompt from the agent's role prompt, shared rules, project `AGENTS.md`, and task context
3. It dispatches to the configured backend (OpenCode, Claude, or human)
4. It waits for the agent to append a new structured block to `handoff.md`
5. It reads the new `NEXT:` field and routes to the appropriate agent
6. It automatically syncs task status in `tasks.json`
7. It stops when `STATUS: plan_complete`, `NEXT: human`, or a blocked state is reached

If an agent fails to update `handoff.md`, the coordinator retries with a targeted reminder before giving up.

## Default agents

The default configuration ships with three agents:

**Architect** — plans the work, assigns tasks, reviews all output, and has final authority over every decision. Can override QA verdicts, challenge results, and request rework from any agent.

**Developer** — implements assigned tasks, runs validation, reports results. Returns to the architect; never skips review.

**QA Engineer** — validates developer work against acceptance criteria. Reports pass/fail with evidence. Returns to the architect, who makes the final call.

```
architect --> developer --> qa_engineer --> architect
                                              |
                            approve / challenge / rework
```

## Requirements

- Python 3.10+
- At least one backend CLI installed and authenticated (opencode, claude, or neither for manual-only)
- No third-party Python packages — standard library only

## Getting started

```bash
git clone https://github.com/zkucekovic/agent-coordinator.git
cd agent-coordinator

# Run with the included example workspace (uses opencode by default)
python3 coordinator.py

# Or point at your own project
python3 coordinator.py --workspace /path/to/your/project --max-turns 20
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--workspace PATH` | `workspace/` | Directory containing `handoff.md` and optionally `tasks.json` |
| `--max-turns N` | 30 | Maximum agent turns before stopping |
| `--reset` | false | Clear saved session IDs and start fresh |
| `--quiet` | false | Suppress per-turn output |

## Setting up a new project workspace

A workspace is a directory with a `handoff.md` file. Everything else is optional.

### 1. Initialize handoff.md

```
---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: architect
TASK_ID: task-000
TITLE: Initialize plan
SUMMARY: Review the project brief and assign the first task.
ACCEPTANCE:
- first task is clearly defined with acceptance criteria
CONSTRAINTS:
- none
FILES_TO_TOUCH:
- handoff.md
CHANGED_FILES:
- n/a
VALIDATION:
- n/a
BLOCKERS:
- none
---END---
```

### 2. Optionally create agents.json

```json
{
  "default_backend": "opencode",
  "retry_policy": {
    "max_rework": 3,
    "on_exceed": "needs_human"
  },
  "agents": {
    "architect": {
      "backend": "opencode",
      "model": null,
      "prompt_file": "prompts/architect.md"
    },
    "developer": {
      "backend": "opencode",
      "model": null,
      "prompt_file": "prompts/developer.md"
    },
    "qa_engineer": {
      "backend": "opencode",
      "model": null,
      "prompt_file": "prompts/qa_engineer.md"
    }
  }
}
```

### 3. Optionally create tasks.json

```json
{
  "tasks": [
    { "id": "task-001", "title": "Implement login endpoint", "status": "planned" }
  ]
}
```

The coordinator auto-syncs task status based on handoff events. Valid states: `planned`, `ready_for_engineering`, `in_engineering`, `ready_for_architect_review`, `rework_requested`, `done`, `blocked`, `needs_human`.

### 4. Run the coordinator

```bash
python3 coordinator.py --workspace /path/to/your/project
```

## Adding agents

To add an agent (e.g. a security reviewer):

1. Create `prompts/security_reviewer.md` — use `prompts/agent_template.md` as a starting point
2. Add the agent to `agents.json` with its backend and model
3. In the relevant prompt files, include `security_reviewer` as a possible `NEXT:` value

The coordinator routes dynamically based on the `NEXT:` field — no code changes required.

## Adding a new backend

Implement the `AgentRunner` interface in `src/application/runner.py`:

```python
from src.application.runner import AgentRunner
from src.domain.models import RunResult

class MyCustomRunner(AgentRunner):
    def run(self, message, workspace, session_id=None, model=None) -> RunResult:
        # Call your backend, return RunResult(session_id="...", text="...")
        ...
```

Register it in the runner factory in `coordinator.py` and use it in `agents.json` with `"backend": "my_custom"`.

## Using your project's AGENTS.md

If an `AGENTS.md` or `agents.md` file exists in the workspace, the coordinator automatically injects it into agent prompts on their first turn. This means your existing coding standards, architecture rules, and testing requirements are enforced without duplication.

The injection order: agent role instructions > project rules (AGENTS.md) > shared protocol rules (shared_rules.md).

## Handoff block format

Every agent turn must end with a structured block:

```
---HANDOFF---
ROLE: architect | developer | qa_engineer | <custom>
STATUS: continue | approved | rework_required | review_required | blocked | needs_human | plan_complete
NEXT: architect | developer | qa_engineer | <custom> | human | none
TASK_ID: task-001
TITLE: Short label
SUMMARY: What was done or decided this turn.
ACCEPTANCE:
- criterion
CONSTRAINTS:
- constraint
FILES_TO_TOUCH:
- src/example.py
CHANGED_FILES:
- src/example.py
VALIDATION:
- python3 -m pytest tests/ -- 42 passed
BLOCKERS:
- none
---END---
```

`handoff.md` is append-only. Agents read the latest block and append their response.

## Human intervention

The workflow stops when any block contains `NEXT: human`. To resume:

1. Read the latest block to understand why it stopped
2. Resolve the issue
3. Append a new block with the correct `NEXT:` value
4. Re-run the coordinator

You can also set an agent's backend to `"manual"` — the coordinator will pause and prompt the human operator directly.

## Running tests

```bash
# Unit tests (188 tests, no external dependencies)
python3 -m unittest discover tests/ -v

# Integration tests (real backend sessions, uses API tokens)
RUN_INTEGRATION_TESTS=1 python3 -m unittest discover tests/integration/ -v
```

## Project structure

```
coordinator.py          entry point and runner factory
agents.json             agent and backend configuration
prompts/
  architect.md          architect system prompt (final authority)
  developer.md          developer system prompt
  qa_engineer.md        QA engineer system prompt
  shared_rules.md       rules all agents must follow
  agent_template.md     template for new agent types
docs/
  ANALYSIS.md           codebase analysis and improvement notes
  protocol.md           handoff block specification
  workflow.md           workflow loop and task lifecycle
scripts/
  parse_next.sh         shell utility: extract NEXT field from handoff.md
src/
  domain/               models, lifecycle rules, retry policy
  application/          task service, router, prompt builder, runner interface
  infrastructure/       file I/O, backend runners (opencode, claude, manual), event log
tests/
  integration/          live backend tests (RUN_INTEGRATION_TESTS=1)
  test_*.py             unit tests (188 tests)
workspace/
  handoff.md            example handoff log
  tasks.json            example task registry
  plan.md               example plan
```

## Further reading

- `docs/protocol.md` — complete handoff block specification and turn rules
- `docs/workflow.md` — full workflow loop, task lifecycle, and session instructions
- `docs/ANALYSIS.md` — codebase analysis, known issues, and improvement ideas
- `prompts/shared_rules.md` — the shared rules all agents must follow
