# Agent Coordinator

Coordinate multiple AI coding agents on the same codebase. Each agent has a role — architect, developer, QA — and they pass work to each other through a shared text file. The coordinator runs the loop: read who's next, build the prompt, dispatch to the right CLI tool, verify the handoff, repeat.

Works with [GitHub Copilot CLI](https://github.com/features/copilot), [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [OpenCode](https://opencode.ai), or any CLI tool you configure. You can mix backends in the same workflow. Zero third-party dependencies — stdlib Python only.

## Why this exists

AI coding agents work one at a time. You open Copilot or Claude, give it a task, wait for it to finish, review the output, then manually start the next step. If you want one agent to plan and another to implement, you copy context between sessions yourself. If you want to use Claude for architecture and Copilot for coding, there's no way to chain them. There's no task tracking, no audit trail, and no way to intervene without starting over.

This tool automates that loop. You define agents in a config file, each backed by whatever CLI tool you want. They communicate through `handoff.md` — a plain text file with structured blocks that any tool can read and write. The coordinator reads who goes next, builds the prompt with the right context, dispatches to the backend, and verifies the agent actually updated the handoff before continuing.

Everything is a file you can read:

- **`handoff.md`** — full conversation history between agents, append-only
- **`tasks.json`** — current state of every task, updated automatically
- **`workflow_events.jsonl`** — audit log of every turn with timestamps

You can pause at any time with Ctrl+C, edit the handoff, inject instructions, or take over a turn yourself.

## Install

```bash
pip install agent-coordinator
```

From source:

```bash
git clone https://github.com/zkucekovic/agent-coordinator.git
cd agent-coordinator
pip install -e .
```

Requires Python 3.10+. Install whichever backend CLI you plan to use.

## Quick start

```bash
# Import a spec and run
agent-coordinator --import SPECIFICATION.md --workspace ./my-project
agent-coordinator --workspace ./my-project

# Or import a plan with tasks already defined
agent-coordinator --import plan.md --workspace ./my-project
agent-coordinator --workspace ./my-project

# Or start from scratch — the coordinator creates an initial handoff
agent-coordinator --workspace ./my-project
```

The default workflow has three agents: an **architect** that plans and reviews, a **developer** that implements, and a **QA engineer** that validates. The architect has final authority — it assigns tasks, routes to QA or back to the developer, and decides when the project is done.

## How it works

Agents communicate through structured blocks in `handoff.md`:

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
CHANGED_FILES:
- src/auth/login.py
- tests/test_login.py
VALIDATION:
- python3 -m pytest tests/test_login.py -- 6 passed
BLOCKERS:
- none
---END---
```

The file is append-only. Each turn, the coordinator:

1. Reads the latest block to find `NEXT:` (who goes next) and `STATUS:` (what's happening)
2. Builds a prompt: role instructions → project rules → spec/plan → shared protocol → handoff history
3. Dispatches to the backend CLI (copilot, claude, opencode, etc.)
4. Verifies the agent appended a new block — retries with a reminder if not
5. Syncs task state in `tasks.json`
6. Logs the turn to `workflow_events.jsonl`

### Status values

| Status | Effect |
|---|---|
| `continue` | Hand off to the next agent |
| `review_required` | Developer finished, architect should review |
| `rework_required` | Changes needed, back to developer |
| `approved` | Architect accepts the work |
| `blocked` | Cannot proceed, needs intervention |
| `needs_human` | Escalate to human operator |
| `plan_complete` | All work done, workflow ends |

### Task lifecycle

```
planned → in_engineering → ready_for_architect_review → done
                ↑                      ↓
          rework_requested ←── (architect decides)
```

## Configuration

### agents.json

```json
{
  "default_backend": "copilot",
  "retry_policy": { "max_rework": 3, "on_exceed": "needs_human" },
  "agents": {
    "architect": {
      "backend": "claude",
      "model": "claude-sonnet-4",
      "prompt_file": "prompts/architect.md"
    },
    "developer": {
      "backend": "copilot",
      "prompt_file": "prompts/developer.md"
    },
    "qa_engineer": {
      "backend": "opencode",
      "prompt_file": "prompts/qa_engineer.md"
    }
  }
}
```

Each agent can use a different backend. `default_backend` applies when an agent doesn't specify one. `max_rework` controls how many rework cycles are allowed before escalating to a human.

Built-in backends: `copilot`, `claude`, `opencode`, `manual` (human-in-the-loop). Any other value is looked up as an executable in PATH, or you can provide a `backend_config` block for full control — see [docs/custom-backends.md](docs/custom-backends.md).

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--workspace PATH` | `workspace/` | Directory with handoff.md and project files |
| `--max-turns N` | `30` | Stop after N agent turns |
| `--reset` | | Clear saved sessions and start fresh |
| `--quiet` | | Suppress TUI output |
| `--output-lines N` | `10` | Agent output lines shown in TUI |
| `--no-streaming` | | Show output all at once instead of streaming |
| `--import FILE` | | Import a specification or plan into workspace |
| `--type spec\|plan` | auto | Force document type when importing |
| `--force` | | Overwrite existing files when importing |

### Project files

Drop these in your workspace and they're automatically injected into agent prompts on first turn:

- **Specification**: `SPECIFICATION.md`, `spec.md`, `PRD.md`, `requirements.md` (first match wins)
- **Plan**: `IMPLEMENTATION_PLAN.md`, `plan.md` (first match wins)
- **Project rules**: `AGENTS.md` — coding standards, conventions, anything agents should follow

All optional. Agents work without them but perform better with explicit context.

### Sessions

Agent session IDs are saved in `<workspace>/.coordinator_sessions.json`. Re-running the coordinator resumes where you left off. Use `--reset` to start clean.

## Interactive control

Press **Ctrl+C** during any turn:

```
  c - Continue execution
  r - Retry current turn
  e - Edit handoff.md in $EDITOR
  m - Add message to handoff
  i - Inspect current state
  q - Quit
```

The workflow also pauses automatically on `NEXT: human` or when `max_rework` is exceeded.

## Adding agents

No code changes needed. Create a prompt, add to config, update routing.

**1.** Create `prompts/security_reviewer.md`:

```markdown
# Security Reviewer

You review code changes for vulnerabilities: hardcoded secrets, injection,
XSS, CSRF, auth/authz issues. Report findings with file, line, and severity.
Do not modify code. NEXT is always architect.
```

**2.** Add to `agents.json`:

```json
"security_reviewer": {
  "backend": "claude",
  "prompt_file": "prompts/security_reviewer.md"
}
```

**3.** Update the architect prompt to route to it when appropriate.

Routing is data-driven — any name in `agents.json` is a valid `NEXT:` target.

## Adding backends

For CLI tools, use `backend_config` in `agents.json` — no Python needed:

```json
"developer": {
  "backend": "custom",
  "backend_config": {
    "command": ["my-cli", "run"],
    "message_arg": "{message}",
    "workspace_arg": ["--dir", "{workspace}"],
    "session_arg": ["--session", "{session_id}"],
    "output_format": "json",
    "json_text_field": "result"
  }
}
```

Or implement the `AgentRunner` interface in Python:

```python
from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.domain.models import RunResult

class MyRunner(AgentRunner):
    def run(self, message, workspace, session_id=None, model=None, on_output=None):
        response = call_my_tool(message)
        return RunResult(session_id="some-id", text=response)
```

Register in `agent_coordinator/cli.py` and reference as `"backend": "my_runner"` in agents.json.

## Retry behavior

When an agent doesn't update `handoff.md` (LLMs sometimes output the block in chat but forget to write the file), the coordinator retries with a targeted reminder. If a task exceeds `max_rework` cycles, it escalates based on the `on_exceed` policy.

## Demo

```bash
agent-coordinator --workspace examples/tetris-demo --max-turns 30
```

Builds a playable HTML Tetris game through the full architect → developer → QA loop. Opens in any browser when done. See [examples/tetris-demo/](examples/tetris-demo/).

## Tests

```bash
python3 -m unittest discover tests/ -v                                      # unit tests
python3 -m unittest tests.test_handoff_parser -v                            # single file
RUN_INTEGRATION_TESTS=1 python3 -m unittest discover tests/integration/ -v  # requires API tokens
```

## Project structure

```
agent_coordinator/
  cli.py                  entry point and orchestration loop
  domain/                 models, task lifecycle, retry policy (no I/O)
  application/            router, prompt builder, task service, runner interface
  infrastructure/         backend runners, PTY subprocess, TUI, file I/O
  handoff_parser.py       regex parser for handoff blocks
  prompts/                role instructions and shared protocol rules
  helpers/                import/export utilities
tests/                    unit and integration tests
docs/                     protocol spec, workflow details, backend guide
examples/                 tetris demo, sample configs
```

## Further reading

- [ARCHITECTURE.md](ARCHITECTURE.md) — hexagonal design, data flow, extension points
- [docs/protocol.md](docs/protocol.md) — handoff block specification
- [docs/workflow.md](docs/workflow.md) — coordinator loop and task lifecycle
- [docs/custom-backends.md](docs/custom-backends.md) — any CLI as a backend
- [docs/interactive-control.md](docs/interactive-control.md) — Ctrl+C menu and human intervention

## License

MIT
