# Agent Coordinator

A framework for running multi-agent AI workflows where each agent has a defined role, a strict communication protocol, and persistent session state across turns.

Agents communicate through a shared `handoff.md` file using a structured, append-only protocol. The coordinator drives the loop automatically — routing each turn to the right agent, maintaining context, logging events, and enforcing task lifecycle rules.

## How it works

Each agent turn follows the same pattern:

1. The coordinator reads `handoff.md` and identifies whose turn it is (`NEXT:` field)
2. It builds a prompt from the agent's system prompt, shared rules, the current handoff log, and optional task context
3. It calls `opencode run` with a persistent session ID, so each agent accumulates context across turns
4. It waits for the agent to append a new structured block to `handoff.md`
5. It reads the new `NEXT:` field and routes to the appropriate agent
6. It stops when `STATUS: plan_complete`, `NEXT: human`, or a blocked state is reached

Every turn is recorded in `workflow_events.jsonl` for auditing.

## Default agents

The default configuration ships with three agents:

**Architect** — plans the work, assigns tasks, reviews all output, and has final authority over every decision. Can override QA verdicts, challenge results, and request rework from any agent.

**Developer** — implements assigned tasks, runs validation, reports results. Returns to the architect; never skips review.

**QA Engineer** — validates developer work against acceptance criteria. Reports pass/fail with evidence. Returns to the architect, who makes the final call.

The standard flow:

```
architect --> developer --> qa_engineer --> architect
                                              |
                            approve / challenge / rework
```

## Requirements

- Python 3.10+
- [opencode](https://opencode.ai) CLI installed and authenticated
- No third-party Python packages — standard library only

## Getting started

```bash
git clone https://github.com/zkucekovic/agent-coordinator.git
cd agent-coordinator

# Run with the included example workspace
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

### 2. Optionally create tasks.json

```json
{
  "tasks": [
    {
      "id": "task-001",
      "title": "Implement login endpoint",
      "status": "planned"
    }
  ]
}
```

Valid status values: `planned`, `ready_for_engineering`, `in_engineering`, `ready_for_architect_review`, `rework_requested`, `done`, `blocked`

### 3. Run the coordinator

```bash
python3 coordinator.py --workspace /path/to/your/project
```

## Adding or customizing agents

Agent configuration lives in `agents.json`:

```json
{
  "retry_policy": {
    "max_rework": 3,
    "on_exceed": "needs_human"
  },
  "agents": {
    "architect": {
      "model": null,
      "prompt_file": "prompts/architect.md"
    },
    "developer": {
      "model": null,
      "prompt_file": "prompts/developer.md"
    },
    "qa_engineer": {
      "model": null,
      "prompt_file": "prompts/qa_engineer.md"
    }
  }
}
```

To add an agent (e.g. a security reviewer):

1. Create `prompts/security_reviewer.md` — use `prompts/agent_template.md` as a starting point
2. Add the agent to `agents.json`
3. In the relevant prompt files, include `security_reviewer` as a possible `NEXT:` value

The coordinator routes dynamically based on the `NEXT:` field — no code changes required.

## Handoff block format

Every agent turn must end with a structured block:

```
---HANDOFF---
ROLE: architect | developer | qa_engineer
STATUS: continue | approved | rework_required | review_required | blocked | needs_human | plan_complete
NEXT: architect | developer | qa_engineer | human | none
TASK_ID: task-001
TITLE: Short label
SUMMARY: What was done or decided this turn.
ACCEPTANCE:
- criterion one
- criterion two
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

`handoff.md` is append-only. Agents read the latest block and append their response — prior history is never modified.

## Human intervention

The workflow stops and waits when any block contains `NEXT: human`. To resume:

1. Read the latest block to understand why it stopped
2. Resolve the issue (answer a question, fix a file, clarify scope)
3. Append a new block manually with the correct `NEXT:` value
4. Re-run the coordinator

You can also intervene proactively at any point by appending a block before the next agent runs.

## Retry policy

When a task exceeds `max_rework` cycles, the coordinator automatically sets its status based on `on_exceed`:

- `"needs_human"` — stops and waits for operator input (default)
- `"blocked"` — marks the task blocked

Configure per project in `agents.json` under `retry_policy`.

## Session persistence

Each agent's OpenCode session ID is saved in `<workspace>/.coordinator_sessions.json`. Re-running the coordinator resumes from where it left off, with full conversation context intact. Use `--reset` to start fresh sessions.

## Event log

Every turn is appended to `<workspace>/workflow_events.jsonl`:

```json
{"ts": "2026-04-05T21:00:00Z", "turn": 1, "agent": "developer", "task_id": "task-001", "status_before": "continue", "status_after": "review_required", "session_id": "ses_abc123"}
```

## Running tests

Unit tests — no external dependencies, no API calls:

```bash
python3 -m unittest discover tests/ -v
```

Integration tests — run real OpenCode sessions (uses tokens):

```bash
RUN_INTEGRATION_TESTS=1 python3 -m unittest discover tests/integration/ -v
```

## Project structure

```
coordinator.py          entry point
agents.json             agent configuration
prompts/
  architect.md          architect system prompt
  developer.md          developer system prompt
  qa_engineer.md        QA engineer system prompt
  shared_rules.md       rules all agents must follow
  agent_template.md     template for new agent types
docs/
  protocol.md           handoff block specification
  workflow.md           workflow loop and task lifecycle
scripts/
  parse_next.sh         shell utility: extract NEXT field from handoff.md
src/
  domain/               models, lifecycle rules, retry policy
  application/          task service, router, prompt builder
  infrastructure/       file I/O, OpenCode subprocess, event log
tests/
  integration/          live OpenCode tests (RUN_INTEGRATION_TESTS=1)
  test_*.py             unit tests
workspace/
  handoff.md            example handoff log
  tasks.json            example task registry
  plan.md               example plan
```

## Further reading

- `docs/protocol.md` — complete handoff block specification and turn rules
- `docs/workflow.md` — full workflow loop, task lifecycle, and session instructions
- `prompts/shared_rules.md` — the shared rules all agents must follow
