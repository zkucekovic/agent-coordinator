# Agent Coordinator

Coordinate multiple AI coding agents — architect, developer, QA — on the same codebase. Agents pass work through `handoff.md`; the coordinator reads who's next, builds the prompt, dispatches to the backend, verifies the handoff, and repeats.

Works with [GitHub Copilot CLI](https://github.com/features/copilot), [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [OpenCode](https://opencode.ai), or any CLI tool. Mix backends freely. Zero third-party dependencies.

Shared files:
- **`handoff.md`** — agent conversation history, append-only
- **`tasks.json`** — task state, updated automatically
- **`.agent-coordinator/`** — coordinator state (sessions, event log, debug log)

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

The default workflow: **architect** plans and reviews, **developer** implements, **QA engineer** validates.

## How it works

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

Each turn: read `NEXT:` → build prompt → dispatch → verify new block appended (retry if not) → sync `tasks.json` → log to `.agent-coordinator/events.jsonl`.

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

Each agent can use a different backend. Built-in: `copilot`, `claude`, `opencode`, `manual` (human-in-the-loop). Any other value is resolved from PATH, or use `backend_config` for full control — see [docs/custom-backends.md](docs/custom-backends.md).

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--workspace PATH` | `.` (cwd) | Directory with handoff.md and project files |
| `--max-turns N` | `30` | Stop after N agent turns |
| `--reset` | | Clear saved sessions and start fresh |
| `--quiet` | | Suppress TUI output |
| `--output-lines N` | `10` | Agent output lines shown in TUI |
| `--no-streaming` | | Show output all at once instead of streaming |
| `--import FILE` | | Import a specification or plan into workspace |
| `--type spec\|plan` | auto | Force document type when importing |
| `--force` | | Overwrite existing files when importing |

### Project files

Drop these in your workspace to inject them into agent prompts on first turn:

- **Specification**: `SPECIFICATION.md`, `spec.md`, `PRD.md`, `requirements.md` (first match wins)
- **Plan**: `IMPLEMENTATION_PLAN.md`, `plan.md` (first match wins)
- **Project rules**: `AGENTS.md` — coding standards and conventions

### Sessions

Session IDs are saved in `<workspace>/.agent-coordinator/sessions.json`. Re-running resumes where you left off. Use `--reset` to start clean.

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

No code changes needed. Create a prompt file, add the agent to `agents.json`, and route to it by writing `NEXT: <role>` in a handoff block.

```json
"security_reviewer": {
  "backend": "claude",
  "prompt_file": "prompts/security_reviewer.md"
}
```

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

If an agent doesn't update `handoff.md`, the coordinator retries with a reminder. If `max_rework` is exceeded, it escalates per the `on_exceed` policy.

## Demo

```bash
agent-coordinator --workspace examples/tetris-demo --max-turns 30
```

Builds a playable HTML Tetris game through the full architect → developer → QA loop. See [examples/tetris-demo/](examples/tetris-demo/).

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
