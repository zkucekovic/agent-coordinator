# Agent Coordinator

Run multi-agent AI workflows across any combination of tools. Define roles, set authority rules, and let the coordinator drive the loop while you watch or step in when needed.

The coordinator is backend-agnostic. It works with GitHub Copilot CLI, OpenCode, Claude Code, or **any custom CLI tool** you configure. You can even mix different backends in the same workflow. The agents don't know about each other — they communicate through a shared, append-only text file (`handoff.md`) using a structured protocol that any tool can read and write.

## The problem

You want multiple AI agents working together on a codebase — one to plan, one to code, one to review. Current options lock you into a single provider's ecosystem, give you no visibility into what's happening between agents, and offer no way to intervene mid-workflow.

This project takes a different approach: the coordination protocol is just text files. The coordinator is a thin loop that reads the protocol and dispatches to whichever backend each agent is configured to use. You can read the full conversation history in `handoff.md`, inspect task state in `tasks.json`, and audit every turn in `workflow_events.jsonl`.

## Installation

```bash
pip install agent-coordinator
```

Or install from source:

```bash
git clone https://github.com/zkucekovic/agent-coordinator.git
cd agent-coordinator
pip install -e .
```

Requirements: Python 3.10+, no third-party packages. Install whichever backend CLI you want to use ([copilot](https://github.com/features/copilot), [opencode](https://opencode.ai), [claude](https://docs.anthropic.com/en/docs/claude-code), or your custom tool).

## Quick start

The fastest way to start is to import an existing document and let the coordinator take it from there.

```bash
# Import a specification — coordinator creates the handoff and starts planning
agent-coordinator --import SPECIFICATION.md --workspace ./my-project

# Import an implementation plan — loads tasks and points the architect at task-001
agent-coordinator --import plan.md --workspace ./my-project

# Run the workflow
agent-coordinator --workspace ./my-project
```

Or start from scratch with an empty workspace — the coordinator auto-creates the initial handoff:

```bash
agent-coordinator --workspace ./my-project
```

## Importing a specification or plan

If you already have a specification document or an implementation plan, import it directly instead of setting things up manually. The coordinator copies the file to the workspace, parses any tasks, and writes an initial `handoff.md` that points the architect to start working.

### Import a specification

```bash
agent-coordinator --import SPECIFICATION.md --workspace ./my-project
```

This:
- Copies `SPECIFICATION.md` to `./my-project/SPECIFICATION.md`
- Creates `handoff.md` instructing the architect to read the spec, write a plan, and decompose tasks

### Import an implementation plan

```bash
agent-coordinator --import plan.md --workspace ./my-project
```

This:
- Copies the plan to `./my-project/plan.md`
- Extracts tasks from the plan headings and writes them to `tasks.json` as `planned`
- Creates `handoff.md` pointing the architect to task-001

Tasks are parsed automatically from common markdown formats:

```markdown
### Phase 1 — Repository setup (task-001)    ← explicit task ID in parentheses
### task-002: Define domain models            ← task ID as heading
### Phase 3: Implement API endpoints          ← numbered phase (auto-assigns task-003)
### 4. Write tests                            ← numbered heading (auto-assigns task-004)
```

### Import flags

| Flag | Description |
|---|---|
| `--import FILE` | Path to the spec or plan file to import |
| `--type spec\|plan` | Force document type (default: auto-detected from content) |
| `--force` | Overwrite existing files in the workspace |
| `--no-handoff` | Copy the file but skip creating `handoff.md` |
| `--no-tasks` | Skip creating `tasks.json` when importing a plan |

After importing, run the coordinator:

```bash
agent-coordinator --workspace ./my-project
```

## Demo: build a Tetris game

The `examples/tetris-demo/` directory contains a ready-to-run demo. It starts from a project brief and produces a fully playable single-file HTML Tetris game through the full architect-developer-QA loop:

```bash
agent-coordinator --workspace examples/tetris-demo --max-turns 30
```

The architect reads the brief, decomposes the work, assigns tasks one at a time, the developer implements, QA validates, and the architect approves or requests rework. When it finishes, open `examples/tetris-demo/tetris.html` in your browser. See [examples/tetris-demo/README.md](examples/tetris-demo/README.md) for details.

## Example: building a feature with three agents

If you prefer to set up a workspace manually, there are two approaches.

### Option A: import a specification

Write a `SPECIFICATION.md` describing what you want built, then import it:

```bash
mkdir my-feature
```

`SPECIFICATION.md`:

```markdown
# User Authentication

## Requirements
- POST /auth/login accepts email and password, returns a signed JWT
- POST /auth/logout invalidates the token server-side
- POST /auth/refresh issues a new JWT before the current one expires
- All endpoints validate input and return appropriate error codes
- All endpoints have unit tests

## Constraints
- Use the existing User model in src/models/user.py
- No new dependencies — use the stdlib jwt module
- Tokens expire after 1 hour
```

```bash
agent-coordinator --import SPECIFICATION.md --workspace ./my-feature
agent-coordinator --workspace ./my-feature --max-turns 20
```

### Option B: write the handoff directly

Put a description in the initial handoff block and the architect will create the spec and plan itself:

```
---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: architect
TASK_ID: task-000
TITLE: Build user authentication
SUMMARY: We need JWT-based auth with login, logout, and token refresh. Use the existing User model. No new dependencies. Write the spec, plan the work, and start building.
ACCEPTANCE:
- specification written to SPECIFICATION.md
- implementation plan created in plan.md
- first task assigned to developer
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

```bash
agent-coordinator --workspace ./my-feature --max-turns 20
```

### What happens automatically

1. The architect reads the specification (or creates one), writes an implementation plan, and assigns the first task to the developer
2. The developer implements the task and hands off to the architect
3. The architect routes to QA for validation
4. QA runs tests, checks acceptance criteria, and reports back to the architect
5. The architect reviews QA's verdict — approves, requests rework, or challenges QA
6. The loop continues until the architect declares `plan_complete`

Each turn is logged in `workflow_events.jsonl`. Task status in `tasks.json` is updated automatically.

## Interactive control

Press **Ctrl+C** at any time during a run to pause and get an interactive menu:

```
INTERRUPTED (Ctrl+C pressed)
──────────────────────────────────────────
  c - Continue execution
  r - Retry current turn
  e - Edit handoff.md in editor
  m - Add message to handoff
  i - Inspect handoff.md
  q - Quit
```

- **Continue** resumes from where you left off
- **Retry** re-runs the current turn without incrementing the turn counter
- **Edit** opens `handoff.md` in your `$EDITOR` so you can correct a bad block or inject instructions
- **Add message** appends a human comment to `handoff.md` before the next turn
- **Inspect** prints the latest handoff block so you can see current state

## Creating tasks and specs interactively

Use the helper commands to create tasks or specifications in your `$EDITOR`:

```bash
# Create a new task (opens in $EDITOR)
python -m agent_coordinator.helpers task --workspace ./my-project

# Create a new specification (opens in $EDITOR)
python -m agent_coordinator.helpers spec --workspace ./my-project

# Import an existing file
python -m agent_coordinator.helpers import plan.md --workspace ./my-project
```

## Example: mixed backends

Use Claude for high-level planning, OpenCode for implementation, and yourself for final review:

```json
{
  "default_backend": "opencode",
  "retry_policy": { "max_rework": 3, "on_exceed": "needs_human" },
  "agents": {
    "architect": {
      "backend": "claude",
      "model": "claude-sonnet-4",
      "prompt_file": "prompts/architect.md"
    },
    "developer": {
      "backend": "opencode",
      "model": null,
      "prompt_file": "prompts/developer.md"
    },
    "qa_engineer": {
      "backend": "manual",
      "model": null,
      "prompt_file": "prompts/qa_engineer.md"
    }
  }
}
```

When it's the QA engineer's turn, the coordinator prints the prompt to your terminal and waits for you to press Enter after you've reviewed the work and appended your handoff block to `handoff.md`.

## Example: adding a security reviewer

No code changes needed. Create a prompt file, add the agent to config, and update existing prompts to route to it.

**1. Create `prompts/security_reviewer.md`** (use `prompts/agent_template.md` as a starting point):

```markdown
# Security Reviewer Agent

You are the **Security Reviewer** in a multi-agent workflow.

## Your Responsibilities
- Review code changes for security vulnerabilities
- Check for hardcoded secrets, SQL injection, XSS, CSRF
- Verify authentication and authorization logic
- Report findings with severity levels

## Rules
- Do not modify code — review only
- NEXT is always `architect`
- Be specific: name the file, line, and vulnerability type
```

**2. Add to `agents.json`:**

```json
"security_reviewer": {
  "backend": "claude",
  "model": null,
  "prompt_file": "prompts/security_reviewer.md"
}
```

**3. Update `prompts/architect.md`** to include `security_reviewer` as a routing option:

```
| Developer work involves auth/crypto | STATUS: continue, NEXT: security_reviewer |
```

The coordinator routes dynamically based on the `NEXT:` field in handoff blocks. Any agent name that exists in `agents.json` is a valid routing target.

## How the protocol works

Agents communicate through `handoff.md`, a plain text file with structured blocks:

```
---HANDOFF---
ROLE: developer
STATUS: review_required
NEXT: architect
TASK_ID: task-001
TITLE: Implement login endpoint
SUMMARY: Added POST /auth/login with JWT signing. Used existing User model.
ACCEPTANCE:
- login endpoint returns a signed JWT — PASS
- input validation on email/password — PASS
CONSTRAINTS:
- used existing database models — followed
CHANGED_FILES:
- src/auth/login.py
- tests/test_login.py
VALIDATION:
- python3 -m pytest tests/test_login.py -- 6 passed
BLOCKERS:
- none
---END---
```

The file is append-only. Each agent reads the latest block, does its work, and appends a new block. The coordinator reads `NEXT:` to know who goes next and `STATUS:` to know whether to continue, stop, or retry.

### Status values

| Status | Meaning |
|---|---|
| `continue` | Normal progression, hand off to the next agent |
| `review_required` | Work is done, needs review by the architect |
| `rework_required` | Work needs changes, goes back to developer |
| `approved` | Architect approves the work |
| `blocked` | Cannot proceed, needs intervention |
| `needs_human` | Escalate to human operator |
| `plan_complete` | All work is done, workflow ends |

### Task lifecycle

If you use `tasks.json`, the coordinator automatically syncs task status based on handoff events:

```
planned → ready_for_engineering → in_engineering → ready_for_architect_review
                                        ↑                       ↓
                                  rework_requested ←──── (architect decides)
                                                                ↓
                                                              done
```

## Configuration reference

### agents.json

```json
{
  "default_backend": "copilot",
  "retry_policy": {
    "max_rework": 3,
    "on_exceed": "needs_human"
  },
  "agents": {
    "agent_name": {
      "backend": "copilot | claude | opencode | manual",
      "model": "model-name or null",
      "prompt_file": "prompts/agent_name.md"
    }
  }
}
```

- `default_backend`: used when an agent doesn't specify its own backend
- `retry_policy.max_rework`: how many rework cycles before escalating (0 = unlimited)
- `retry_policy.on_exceed`: what happens when the limit is hit (`needs_human` or `blocked`)

### CLI options

**Running a workflow:**

| Flag | Default | Description |
|---|---|---|
| `--workspace PATH` | `workspace/` | Directory with `handoff.md` and project files |
| `--max-turns N` | 30 | Maximum agent turns before stopping |
| `--reset` | false | Clear saved session IDs and start fresh |
| `--quiet` | false | Suppress TUI output |
| `--output-lines N` | 10 | Lines of agent output shown in the TUI window |
| `--no-streaming` | false | Print agent output all at once instead of streaming |

**Importing a document:**

| Flag | Default | Description |
|---|---|---|
| `--import FILE` | — | Import a specification or implementation plan |
| `--type spec\|plan` | auto-detect | Force document type |
| `--force` | false | Overwrite existing files |
| `--no-handoff` | false | Skip creating `handoff.md` |
| `--no-tasks` | false | Skip creating `tasks.json` (plan imports only) |

### Session persistence

Each agent's session ID is saved in `<workspace>/.coordinator_sessions.json`. Re-running the coordinator resumes conversations with full context. Use `--reset` to start fresh.

## Project files: specification, plan, and AGENTS.md

The coordinator automatically detects and injects key project files into agent prompts on their first turn. No configuration needed — just place the files in your workspace (or use `--import` to set them up).

**Specification files** (checked in order, first match wins):
`SPECIFICATION.md`, `specification.md`, `spec.md`, `SPEC.md`, `PRD.md`, `prd.md`, `requirements.md`, `REQUIREMENTS.md`

**Implementation plan files** (checked in order, first match wins):
`IMPLEMENTATION_PLAN.md`, `implementation_plan.md`, `plan.md`, `PLAN.md`

**Project rules**:
`AGENTS.md` or `agents.md`

The spec and plan give agents the context they need to understand the project. The AGENTS.md file enforces your existing coding standards. All three are optional — the coordinator works without them, but agents perform better with explicit requirements.

Injection order in the prompt: role instructions > project rules (AGENTS.md) > specification and plan > shared protocol rules.

## Adding a new backend

Implement the `AgentRunner` interface:

```python
from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.domain.models import RunResult

class MyRunner(AgentRunner):
    def run(self, message, workspace, session_id=None, model=None, on_output=None) -> RunResult:
        response = call_my_tool(message)
        return RunResult(session_id="some-id", text=response)
```

Register it in the runner factory in `agent_coordinator/cli.py` and reference it in `agents.json` as `"backend": "my_runner"`.

For fully configurable CLI tools, use `GenericRunner` via `backend_config` in `agents.json` without writing any Python — see [docs/custom-backends.md](docs/custom-backends.md).

## Human intervention

The workflow pauses when `NEXT: human` appears. To resume:

1. Read the latest block in `handoff.md` to see why it stopped
2. Fix the issue or answer the question
3. Append a new handoff block with `NEXT:` pointing to the right agent
4. Re-run the coordinator

You can also intervene proactively — press Ctrl+C during any turn to edit `handoff.md`, add a message, or retry the current turn.

## Retry behavior

When an agent's response doesn't update `handoff.md` (common with LLMs that output the block in chat but don't write it to the file), the coordinator automatically retries with a targeted reminder. If a task exceeds `max_rework` cycles, the coordinator escalates based on the `on_exceed` policy.

## Running tests

```bash
# Unit tests (no API calls, no dependencies)
python3 -m unittest discover tests/ -v

# Single test file
python3 -m unittest tests.test_handoff_parser -v

# Integration tests (runs real agent sessions, requires API tokens)
RUN_INTEGRATION_TESTS=1 python3 -m unittest discover tests/integration/ -v
```

## Project structure

```
pyproject.toml            package configuration (pip install)
coordinator.py            backwards-compatible entry point
agents.json               default agent and backend configuration
agent_coordinator/
  cli.py                  CLI entry point and orchestration loop
  prompts/                prompt templates (shipped with package)
    architect.md          architect prompt (final authority)
    developer.md          developer prompt
    qa_engineer.md        QA engineer prompt
    shared_rules.md       protocol rules all agents follow
    agent_template.md     starting point for new agent types
  helpers/                helper commands
    import_plan.py        --import: parse and load specs and plans
    create_task.py        task/spec creation helpers
  domain/                 models, task lifecycle, retry policy
  application/            task service, router, prompt builder, runner interface
  infrastructure/         backend runners, file I/O, TUI, event log
tests/
  test_*.py               unit tests
  integration/            live backend tests
docs/
  protocol.md             handoff block specification
  workflow.md             coordinator loop and task lifecycle
  custom-backends.md      how to configure any CLI as a backend
  interactive-control.md  Ctrl+C menu usage
examples/
  tetris-demo/            ready-to-run demo that builds a Tetris game
workspace/                example workspace with sample handoff and tasks
```

## How this relates to Google's A2A protocol

Google's [Agent-to-Agent (A2A) protocol](https://github.com/a2aproject/A2A) and this project solve different problems at different layers.

A2A is an inter-service protocol. It uses HTTP, gRPC, and Server-Sent Events to connect agents across networks and organizations. Agents discover each other at runtime through Agent Cards (JSON endpoints), authenticate via enterprise security schemes, and exchange structured JSON-RPC messages. It's designed for distributed systems where Agent A at Company X needs to talk to Agent B at Company Y.

Agent Coordinator is a local workflow protocol. It coordinates multiple AI coding agents working on the same codebase on one machine. There is no network layer, no service discovery, no authentication. Agents communicate through a shared file on disk (`handoff.md`), and the coordinator dispatches to local CLI tools. It's designed for a developer who wants an architect to plan, a developer to code, and a QA engineer to review — all running on their laptop.

| | A2A | Agent Coordinator |
|---|---|---|
| Scope | Cross-network, cross-organization | Single machine, single codebase |
| Transport | HTTP/gRPC/SSE | Shared files on disk |
| Discovery | Agent Cards (JSON endpoints) | `agents.json` config file |
| Dependencies | Enterprise-grade (auth, TLS, streaming) | Zero — stdlib Python only |
| Use case | Distributed agent services | Local multi-agent dev workflows |

The two are complementary. A2A defines how agents talk across boundaries. Agent Coordinator defines how agents collaborate on a shared task locally. An Agent Coordinator backend could be an A2A client — dispatching turns to a remote A2A-compliant agent instead of a local CLI. The `AgentRunner` interface already supports this: implement `run()` to call an A2A endpoint, register it as a backend, and remote agents participate in the same local workflow alongside local ones.

## Further reading

- [docs/protocol.md](docs/protocol.md) — handoff block specification and parsing rules
- [docs/workflow.md](docs/workflow.md) — coordinator loop, task lifecycle, and session management
- [docs/custom-backends.md](docs/custom-backends.md) — configure any CLI tool as a backend
- [docs/interactive-control.md](docs/interactive-control.md) — Ctrl+C menu and human intervention
- [prompts/shared_rules.md](prompts/shared_rules.md) — the 10 rules all agents must follow

```bash
pip install agent-coordinator
```

Or install from source:

```bash
git clone https://github.com/zkucekovic/agent-coordinator.git
cd agent-coordinator
pip install -e .
```

Requirements: Python 3.10+, no third-party packages. Install whichever backend CLI you want to use ([copilot](https://github.com/features/copilot), [opencode](https://opencode.ai), [claude](https://docs.anthropic.com/en/docs/claude-code), or your custom tool).

## Quick start

```bash
# Run with GitHub Copilot CLI (default)
agent-coordinator --workspace /path/to/your/project

# Or with OpenCode
# (set default_backend in agents.json to "opencode")
agent-coordinator --workspace /path/to/your/project

# Or with Claude Code
# (set default_backend in agents.json to "claude")
agent-coordinator --workspace /path/to/your/project

# Or with your custom CLI tool
# (configure backend_config in agents.json - see docs/custom-backends.md)
agent-coordinator --workspace /path/to/your/project

# Or run fully manual to see what prompts get generated
# (set default_backend to "manual")
agent-coordinator --workspace /path/to/your/project
```

### What's New

**Interactive Control**: Press Ctrl+C at any time to:
- Continue, retry, or quit
- **Edit handoff.md in your editor** (vim, vscode, etc.)
- Add human guidance
- Inspect current state

**Human Agent**: Agents can request human input with `NEXT: human` - coordinator prompts you to edit in your preferred editor.

**Auto-Initialize**: No handoff.md? No problem. The coordinator creates one automatically and starts the workflow.

**Enhanced Observability**: Clean TUI with animated thinking indicator `[⠹]` - know when agents are working!

**Editor-Based Creation**: Create tasks and specs in your preferred text editor:
```bash
python -m agent_coordinator.helpers task --workspace ./my-project   # Opens in $EDITOR
python -m agent_coordinator.helpers spec --workspace ./my-project   # Natural editing
```

**Custom Backend Support**: Use any CLI tool as backend - GitHub Copilot (default), OpenCode, Claude, or your own.

See [docs/interactive-control.md](docs/interactive-control.md), [docs/editor-integration.md](docs/editor-integration.md), [docs/human-agent.md](docs/human-agent.md), and [docs/custom-backends.md](docs/custom-backends.md) for details.

## Demo: build a Tetris game

The `examples/tetris-demo/` directory contains a ready-to-run demo. It starts from a project brief and produces a fully playable single-file HTML Tetris game through the full architect-developer-QA loop:

```bash
agent-coordinator --workspace examples/tetris-demo --max-turns 30
```

The architect reads the brief, decomposes the work, assigns tasks one at a time, the developer implements, QA validates, and the architect approves or requests rework. When it finishes, open `examples/tetris-demo/tetris.html` in your browser. See [examples/tetris-demo/README.md](examples/tetris-demo/README.md) for details.

## Example: building a feature with three agents

The coordinator is designed to work from project specifications and implementation plans. You can either provide these upfront, or let the architect create them.

### Option A: provide a specification

Write a `SPECIFICATION.md` in your workspace describing what you want built. The architect reads it, creates an implementation plan (`plan.md`), and starts assigning tasks.

```bash
mkdir my-feature && cd my-feature
```

Create `SPECIFICATION.md`:

```markdown
# User Authentication

## Requirements
- POST /auth/login accepts email and password, returns a signed JWT
- POST /auth/logout invalidates the token server-side
- POST /auth/refresh issues a new JWT before the current one expires
- All endpoints validate input and return appropriate error codes
- All endpoints have unit tests

## Constraints
- Use the existing User model in src/models/user.py
- No new dependencies — use the stdlib jwt module
- Tokens expire after 1 hour
```

Create `handoff.md`:

```
---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: architect
TASK_ID: task-000
TITLE: Build user authentication
SUMMARY: Read SPECIFICATION.md and create an implementation plan. Decompose into tasks and begin.
ACCEPTANCE:
- specification has been read
- implementation plan created in plan.md
- first task assigned to developer
CONSTRAINTS:
- none
FILES_TO_TOUCH:
- handoff.md
- plan.md
- tasks.json
CHANGED_FILES:
- n/a
VALIDATION:
- n/a
BLOCKERS:
- none
---END---
```

### Option B: describe it in the handoff

If you don't have a spec, put a general description in the initial handoff. The architect will create the specification and plan before starting work.

```
---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: architect
TASK_ID: task-000
TITLE: Build user authentication
SUMMARY: We need JWT-based auth with login, logout, and token refresh. Use the existing User model. No new dependencies. Write the spec, plan the work, and start building.
ACCEPTANCE:
- specification written to SPECIFICATION.md
- implementation plan created in plan.md
- first task assigned to developer
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

### Running the workflow

```bash
agent-coordinator --workspace ./my-feature --max-turns 20
```

What happens next, automatically:

1. The architect reads the specification (or creates one), writes an implementation plan, and assigns the first task to the developer
2. The developer implements the task and hands off to the architect
3. The architect routes to QA for validation
4. QA runs tests, checks acceptance criteria, and reports back to the architect
5. The architect reviews QA's verdict — approves, requests rework, or challenges QA
6. The loop continues until the architect declares `plan_complete`

Each turn is logged in `workflow_events.jsonl`. Task status in `tasks.json` is updated automatically.

## Example: mixed backends

Use Claude for high-level planning, OpenCode for implementation, and yourself for final review:

```json
{
  "default_backend": "opencode",
  "retry_policy": { "max_rework": 3, "on_exceed": "needs_human" },
  "agents": {
    "architect": {
      "backend": "claude",
      "model": "claude-sonnet-4",
      "prompt_file": "prompts/architect.md"
    },
    "developer": {
      "backend": "opencode",
      "model": null,
      "prompt_file": "prompts/developer.md"
    },
    "qa_engineer": {
      "backend": "manual",
      "model": null,
      "prompt_file": "prompts/qa_engineer.md"
    }
  }
}
```

When it's the QA engineer's turn, the coordinator prints the prompt to your terminal and waits for you to press Enter after you've reviewed the work and appended your handoff block to `handoff.md`.

## Example: adding a security reviewer

No code changes needed. Create a prompt file, add the agent to config, and update existing prompts to route to it.

**1. Create `prompts/security_reviewer.md`** (use `prompts/agent_template.md` as a starting point):

```markdown
# Security Reviewer Agent

You are the **Security Reviewer** in a multi-agent workflow.

## Your Responsibilities
- Review code changes for security vulnerabilities
- Check for hardcoded secrets, SQL injection, XSS, CSRF
- Verify authentication and authorization logic
- Report findings with severity levels

## Rules
- Do not modify code — review only
- NEXT is always `architect`
- Be specific: name the file, line, and vulnerability type
```

**2. Add to `agents.json`:**

```json
"security_reviewer": {
  "backend": "claude",
  "model": null,
  "prompt_file": "prompts/security_reviewer.md"
}
```

**3. Update `prompts/architect.md`** to include `security_reviewer` as a routing option:

```
| Developer work involves auth/crypto | STATUS: continue, NEXT: security_reviewer |
```

The coordinator routes dynamically based on the `NEXT:` field in handoff blocks. Any agent name that exists in `agents.json` is a valid routing target.

## How the protocol works

Agents communicate through `handoff.md`, a plain text file with structured blocks:

```
---HANDOFF---
ROLE: developer
STATUS: review_required
NEXT: architect
TASK_ID: task-001
TITLE: Implement login endpoint
SUMMARY: Added POST /auth/login with JWT signing. Used existing User model.
ACCEPTANCE:
- login endpoint returns a signed JWT — PASS
- input validation on email/password — PASS
CONSTRAINTS:
- used existing database models — followed
CHANGED_FILES:
- src/auth/login.py
- tests/test_login.py
VALIDATION:
- python3 -m pytest tests/test_login.py -- 6 passed
BLOCKERS:
- none
---END---
```

The file is append-only. Each agent reads the latest block, does its work, and appends a new block. The coordinator reads `NEXT:` to know who goes next and `STATUS:` to know whether to continue, stop, or retry.

### Status values

| Status | Meaning |
|---|---|
| `continue` | Normal progression, hand off to the next agent |
| `review_required` | Work is done, needs review by the architect |
| `rework_required` | Work needs changes, goes back to developer |
| `approved` | Architect approves the work |
| `blocked` | Cannot proceed, needs intervention |
| `needs_human` | Escalate to human operator |
| `plan_complete` | All work is done, workflow ends |

### Task lifecycle

If you use `tasks.json`, the coordinator automatically syncs task status based on handoff events:

```
planned → ready_for_engineering → in_engineering → ready_for_architect_review
                                        ↑                       ↓
                                  rework_requested ←──── (architect decides)
                                                                ↓
                                                              done
```

## Configuration reference

### agents.json

```json
{
  "default_backend": "opencode",
  "retry_policy": {
    "max_rework": 3,
    "on_exceed": "needs_human"
  },
  "agents": {
    "agent_name": {
      "backend": "opencode | claude | manual",
      "model": "model-name or null",
      "prompt_file": "prompts/agent_name.md"
    }
  }
}
```

- `default_backend`: used when an agent doesn't specify its own backend
- `retry_policy.max_rework`: how many rework cycles before escalating
- `retry_policy.on_exceed`: what happens when max rework is exceeded (`needs_human` or `blocked`)

### CLI options

| Flag | Default | Description |
|---|---|---|
| `--workspace PATH` | `workspace/` | Directory with `handoff.md` and project files |
| `--max-turns N` | 30 | Maximum agent turns before stopping |
| `--reset` | false | Clear saved session IDs and start fresh |
| `--quiet` | false | Suppress per-turn output |

### Session persistence

Each agent's session ID is saved in `<workspace>/.coordinator_sessions.json`. Re-running the coordinator resumes conversations with full context. Use `--reset` to start fresh.

## Project files: specification, plan, and AGENTS.md

The coordinator automatically detects and injects key project files into agent prompts on their first turn. No configuration needed — just place the files in your workspace.

**Specification files** (checked in order, first match wins):
`SPECIFICATION.md`, `specification.md`, `spec.md`, `SPEC.md`, `PRD.md`, `prd.md`, `requirements.md`, `REQUIREMENTS.md`

**Implementation plan files** (checked in order, first match wins):
`IMPLEMENTATION_PLAN.md`, `implementation_plan.md`, `plan.md`, `PLAN.md`

**Project rules**:
`AGENTS.md` or `agents.md`

The spec and plan give agents the context they need to understand the project. The AGENTS.md file enforces your existing coding standards. All three are optional — the coordinator works without them, but agents perform better with explicit requirements.

Injection order in the prompt: role instructions > project rules (AGENTS.md) > specification and plan > shared protocol rules.

## Adding a new backend

Implement the `AgentRunner` interface:

```python
from src.application.runner import AgentRunner
from src.domain.models import RunResult

class MyRunner(AgentRunner):
    def run(self, message, workspace, session_id=None, model=None) -> RunResult:
        # Dispatch to your tool, return the response
        response = call_my_tool(message)
        return RunResult(session_id="some-id", text=response)
```

Register it in the runner factory in `coordinator.py` and reference it in `agents.json` as `"backend": "my_runner"`.

## Human intervention

The workflow pauses when `NEXT: human` appears. To resume:

1. Read the latest block in `handoff.md` to see why it stopped
2. Fix the issue or answer the question
3. Append a new handoff block with `NEXT:` pointing to the right agent
4. Re-run the coordinator

You can also intervene proactively by appending a block before the next turn runs.

## Retry behavior

When an agent's response doesn't update `handoff.md` (common with LLMs that output the block in chat but don't write it to the file), the coordinator automatically retries with a targeted reminder. If a task exceeds `max_rework` cycles, the coordinator escalates based on the `on_exceed` policy.

## Running tests

```bash
# Unit tests (188 tests, no API calls, no dependencies)
python3 -m unittest discover tests/ -v

# Integration tests (runs real agent sessions, uses API tokens)
RUN_INTEGRATION_TESTS=1 python3 -m unittest discover tests/integration/ -v
```

## Project structure

```
pyproject.toml            package configuration (pip install)
coordinator.py            backwards-compatible entry point
agents.json               default agent and backend configuration
agent_coordinator/
  cli.py                  CLI entry point and orchestration loop
  prompts/                prompt templates (shipped with package)
    architect.md          architect prompt (final authority)
    developer.md          developer prompt
    qa_engineer.md        QA engineer prompt
    shared_rules.md       protocol rules all agents follow
    agent_template.md     starting point for new agent types
  domain/                 models, task lifecycle, retry policy
  application/            task service, router, prompt builder, runner interface
  infrastructure/         backend runners (opencode, claude, manual), file I/O, event log
tests/
  test_*.py               unit tests
  integration/            live backend tests
docs/
  protocol.md             handoff block specification
  workflow.md             workflow loop and task lifecycle details
examples/
  tetris-demo/            ready-to-run demo that builds a Tetris game
workspace/                example workspace with sample handoff and tasks
```

## How this relates to Google's A2A protocol

Google's [Agent-to-Agent (A2A) protocol](https://github.com/a2aproject/A2A) and this project solve different problems at different layers.

A2A is an inter-service protocol. It uses HTTP, gRPC, and Server-Sent Events to connect agents across networks and organizations. Agents discover each other at runtime through Agent Cards (JSON endpoints), authenticate via enterprise security schemes, and exchange structured JSON-RPC messages. It's designed for distributed systems where Agent A at Company X needs to talk to Agent B at Company Y.

Agent Coordinator is a local workflow protocol. It coordinates multiple AI coding agents working on the same codebase on one machine. There is no network layer, no service discovery, no authentication. Agents communicate through a shared file on disk (`handoff.md`), and the coordinator dispatches to local CLI tools. It's designed for a developer who wants an architect to plan, a developer to code, and a QA engineer to review — all running on their laptop.

| | A2A | Agent Coordinator |
|---|---|---|
| Scope | Cross-network, cross-organization | Single machine, single codebase |
| Transport | HTTP/gRPC/SSE | Shared files on disk |
| Discovery | Agent Cards (JSON endpoints) | `agents.json` config file |
| Dependencies | Enterprise-grade (auth, TLS, streaming) | Zero — stdlib Python only |
| Use case | Distributed agent services | Local multi-agent dev workflows |

The two are complementary. A2A defines how agents talk across boundaries. Agent Coordinator defines how agents collaborate on a shared task locally. An Agent Coordinator backend could be an A2A client — dispatching turns to a remote A2A-compliant agent instead of a local CLI. The `AgentRunner` interface already supports this: implement `run()` to call an A2A endpoint, register it as a backend, and remote agents participate in the same local workflow alongside local ones.

## Further reading

- [docs/protocol.md](docs/protocol.md) — handoff block specification and parsing rules
- [docs/workflow.md](docs/workflow.md) — coordinator loop, task lifecycle, and session management
- [prompts/shared_rules.md](prompts/shared_rules.md) — the 10 rules all agents must follow
