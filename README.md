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
```bash
uv run pipx install agent-coordinator
```

From source:

```bash
git clone https://github.com/zkucekovic/agent-coordinator.git
cd agent-coordinator
pip install -e .
```

Requires Python 3.10+. Install whichever backend CLI you plan to use.

## Quick start

### Option A — Start from scratch

```bash
# Initialise a new workspace (creates handoff.md + agents.json automatically)
agent-coordinator --workspace ./my-project
```

The coordinator creates two files in `./my-project/`:

**`agents.json`** — ready to run, no editing needed:
```json
{
  "default_backend": "copilot",
  "retry_policy": { "max_rework": 3, "on_exceed": "needs_human" },
  "agents": {
    "architect":   { "backend": "copilot", "model": "claude-sonnet-4.6", "prompt_file": "prompts/architect.md", "supportsStatelessMode": false },
    "developer":   { "backend": "copilot", "model": "claude-sonnet-4.6", "prompt_file": "prompts/developer.md", "supportsStatelessMode": true },
    "qa_engineer": { "backend": "copilot", "model": "claude-sonnet-4.6", "prompt_file": "prompts/qa_engineer.md", "supportsStatelessMode": true }
  }
}
```

**`handoff.md`** — initial handoff directing the architect to start planning.

Then drop in your project context and hit **Start**:

```bash
# Add a spec and/or plan (optional — agents will work from handoff.md otherwise)
cp SPECIFICATION.md ./my-project/
cp plan.md ./my-project/

# Run — the startup menu appears; press Enter to start
agent-coordinator --workspace ./my-project
```

---

### Option B — Import specs and plans, then run

Import your existing documents and let the architect pick up immediately:

```bash
# Import a single spec or plan (auto-detected)
agent-coordinator --import SPECIFICATION.md --workspace ./my-project
agent-coordinator --import plan.md --workspace ./my-project

# Import entire folders
agent-coordinator --import-specs ./specs/ --workspace ./my-project
agent-coordinator --import-plans ./plans/ --workspace ./my-project

# Then start the coordinator
agent-coordinator --workspace ./my-project
```

On first run the coordinator injects all spec/plan files into the architect's prompt. The architect reads them, decomposes the work into `tasks.json`, and hands off task-001 to the developer.

---

### The development loop

Once running, each turn follows this cycle:

```
architect  →  reads spec/plan, creates tasks.json, assigns task-001 to developer
developer  →  implements the task, writes code, updates handoff.md (STATUS: review_required)
architect  →  reviews the work (STATUS: approved or rework_required)
qa_engineer → validates, runs tests, writes handoff.md (STATUS: continue or blocked)
              ↑ repeat for each task
```

**Working through a task list:**

The coordinator tracks `tasks.json` automatically. After each approved task the architect assigns the next one. You can watch progress live in the TUI or check `tasks.json`:

```json
{ "id": "task-001", "title": "...", "status": "done" },
{ "id": "task-002", "title": "...", "status": "in_engineering" },
{ "id": "task-003", "title": "...", "status": "planned" }
```

To skip to a specific task or add context, press **Ctrl+C** → **m** (add message to handoff) and type your instruction.

---

### Skip the menu — run immediately

```bash
agent-coordinator --workspace ./my-project --auto          # skip startup menu
agent-coordinator --workspace ./my-project --max-turns 20  # stop after 20 turns
agent-coordinator --workspace ./my-project --reset         # clear sessions and restart
```



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
      "prompt_file": "prompts/architect.md",
      "supportsStatelessMode": false
    },
    "developer": {
      "backend": "copilot",
      "prompt_file": "prompts/developer.md",
      "supportsStatelessMode": true
    },
    "qa_engineer": {
      "backend": "opencode",
      "prompt_file": "prompts/qa_engineer.md",
      "supportsStatelessMode": true
    }
  }
}
```

Each agent can use a different backend. Built-in: `copilot`, `claude`, `opencode`, `manual` (human-in-the-loop). Any other value is resolved from PATH, or use `backend_config` for full control — see [docs/custom-backends.md](docs/custom-backends.md). Set `supportsStatelessMode: false` for agents that should keep their session even when the CLI runs with `--stateless`.

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--workspace PATH` | `.` (cwd) | Directory with handoff.md and project files |
| `--max-turns N` | `0` (unlimited) | Stop after N agent turns (0 = run until done) |
| `--reset` | | Clear saved sessions and start fresh |
| `--auto` | | Skip the startup menu and run immediately |
| `--quiet` | | Suppress TUI output |
| `--output-lines N` | `10` | Agent output lines shown in TUI |
| `--no-streaming` | | Show output all at once instead of streaming |
| `--stateless` | | Run supported agents without session persistence (fresh context every turn) |
| `--import FILE` | | Import a single specification or plan file into workspace |
| `--import-specs PATH` | | Import a directory (or file) of specs into `<workspace>/specs/` |
| `--import-plans PATH` | | Import a directory (or file) of plans into `<workspace>/plans/` (also extracts `tasks.json`) |
| `--type spec\|plan` | auto | Force document type when using `--import` |
| `--force` | | Overwrite existing files when importing |
| `--no-handoff` | | Skip creating handoff.md when importing |
| `--no-tasks` | | Skip creating tasks.json when importing a plan |

### Project files

Drop these in your workspace — they're injected into agent prompts on the first turn:

- **Spec folder**: `specs/`, `spec/`, or `specifications/` — all `.md` files loaded
- **Plan folder**: `plans/`, `plan/`, or `implementation_plans/` — all `.md` files loaded
- **Single spec file** (fallback): `SPECIFICATION.md`, `spec.md`, `PRD.md`, `requirements.md`
- **Single plan file** (fallback): `IMPLEMENTATION_PLAN.md`, `plan.md`
- **Project rules**: `AGENTS.md` — coding standards, conventions, and constraints

Folders take priority over single files. Use `--import-specs` / `--import-plans` to populate these from outside the workspace.

### Sessions

Session IDs are saved in `<workspace>/.agent-coordinator/sessions.json`. Re-running resumes where you left off. Use `--reset` to start clean. With `--stateless`, only agents whose config allows stateless mode get a fresh context every turn; agents with `supportsStatelessMode: false` keep using their saved sessions.

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
