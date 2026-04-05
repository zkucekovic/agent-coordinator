# Agent Coordinator

A multi-agent workflow system where an **Architect**, **Developer**, and **QA Engineer** collaborate on software delivery through a shared `handoff.md` file. All communication is structured, append-only, and machine-parseable.

**`coordinator.py` drives all agents automatically** using real OpenCode sessions — the full loop runs hands-free until `plan_complete`.

## Requirements

- **Python 3.10+** (uses union type syntax: `X | None`)
- **`opencode` CLI** installed (for `coordinator.py`)
- No other external packages — standard library only

## Directory Structure

```
coordination/
  coordinator.py        ← drives OpenCode sessions automatically
  agents.json           ← agent configuration (models, prompt files, retry policy)
  prompts/
    architect.md        ← architect system prompt
    developer.md        ← developer system prompt
    qa_engineer.md      ← QA engineer system prompt
    shared_rules.md     ← rules all agents must follow
    agent_template.md   ← template for adding new agent types
  docs/
    protocol.md         ← handoff block format specification
    workflow.md         ← full workflow loop and task lifecycle
  scripts/
    parse_next.sh       ← extract NEXT: field from handoff.md (shell automation)
  src/
    domain/             ← models, lifecycle rules, retry policy
    application/        ← task service, router, prompt builder
    infrastructure/     ← file I/O, OpenCode runner, event log
  tests/
    integration/        ← real OpenCode session tests (RUN_INTEGRATION_TESTS=1)
    test_*.py           ← unit tests
  workspace/            ← example project workspace
    handoff.md          ← append-only agent communication log
    tasks.json          ← task registry with lifecycle status
    plan.md             ← implementation plan
```

> **Important:** All `python3` commands and imports must be run from inside the `coordination/` directory. The `src` package is not installed globally.

---

## Running Tests

```bash
cd coordination/
python3 -m unittest discover tests/ -v
```

Expected: `Ran 35 tests in ~0.003s — OK`

---

## Inspecting the Current Workflow State

```bash
cd coordination/
python3 -c "
from src.workflow import get_workflow_state
import json
state = get_workflow_state('handoff.md')
print(json.dumps(state, indent=2))
"
```

Example output:

```json
{
  "valid": true,
  "next_actor": "engineer",
  "status": "continue",
  "task_id": "task-003",
  "is_complete": false,
  "is_blocked": false,
  "needs_human": false,
  "errors": []
}
```

Use this to quickly check whose turn it is and whether the workflow needs human attention.

---

## Automated Mode: coordinator.py

`coordinator.py` drives the full multi-agent loop automatically using real OpenCode (`opencode run`) sessions. No manual copy-pasting required.

### Quick Start

```bash
cd /path/to/coordination/

# Use the built-in example workspace (workspace/ directory)
python3 coordinator.py

# Or point at your own project workspace
python3 coordinator.py --workspace /path/to/myproject --max-turns 20
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--workspace PATH` | `workspace/` | Directory containing `handoff.md` and optionally `tasks.json` |
| `--max-turns N` | 30 | Safety limit on total agent turns |
| `--reset` | false | Delete `.coordinator_sessions.json` and start fresh sessions |
| `--quiet` | false | Suppress per-turn verbose output |

### What it does

1. Reads `handoff.md` to determine whose turn it is (`NEXT:` field of the latest block)
2. Builds a prompt: role-specific system prompt + shared rules + full handoff.md + task context
3. Calls `opencode run` with `--session <id>` so each agent maintains persistent context
4. Waits for the agent to append a new `---HANDOFF---` block to `handoff.md`
5. Routes to the next agent based on the new `NEXT:` field
6. Stops when `STATUS: plan_complete`, `NEXT: human`, or `blocked` is detected

Session IDs are saved in `<workspace>/.coordinator_sessions.json` — re-running the script continues where it left off unless `--reset` is passed.

### Real example

```
$ python3 coordinator.py --workspace /tmp/myproject --max-turns 6

[Turn 1] status=continue  next=architect  task=task-000
  Agent: ARCHITECT
  ✓ handoff.md updated → status=continue, next=engineer

[Turn 2] status=continue  next=engineer  task=task-001
  Agent: ENGINEER
  ✓ handoff.md updated → status=review_required, next=architect

[Turn 3] status=review_required  next=architect  task=task-001
  Agent: ARCHITECT
  ✓ handoff.md updated → status=plan_complete, next=human

✅  PLAN COMPLETE — workflow finished successfully.
  Total turns:     3
  Architect turns: 2
  Engineer turns:  1
```

---

## Starting a New Project

### 1. Create `tasks.json`

The task registry must be a JSON object with a `"tasks"` array:

```json
{
  "tasks": [
    {
      "id": "task-001",
      "title": "Initialize project structure",
      "status": "planned",
      "acceptance_criteria": []
    },
    {
      "id": "task-002",
      "title": "Implement core logic",
      "status": "planned",
      "acceptance_criteria": []
    }
  ]
}
```

Valid `status` values: `planned`, `ready_for_engineering`, `in_engineering`, `ready_for_architect_review`, `rework_requested`, `done`, `blocked`

### 2. Initialize `handoff.md`

```bash
cat > handoff.md << 'EOF'
# Handoff Log

This file is append-only.

## Initial State

Human operator initialized the workflow.

---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: architect
TASK_ID: task-000
TITLE: Initialize plan
SUMMARY: Review the project brief and assign the first engineering task.
ACCEPTANCE:
- first task is clearly defined
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
EOF
```

### 3. Run the Coordinator (Automatic)

```bash
cd /path/to/coordination/
python3 coordinator.py --workspace /path/to/your-project
```

The coordinator drives both agents until `plan_complete`. See the [Automated Mode](#automated-mode-coordinatorpy) section above.

### 3b. Manual Mode

If you prefer to drive agents yourself:

Copy the contents of `prompts/architect.md` and paste it as the system prompt (or first message) into your architect agent. Then give the agent:

- the current `handoff.md`
- the project brief or spec

The architect will append a task assignment to `handoff.md`.

### 4. Start the Engineer Session (Manual only)

Copy the contents of `prompts/developer.md` (or `prompts/qa_engineer.md`) and `prompts/shared_rules.md` into the relevant agent session. Give it:

- the current `handoff.md`
- access to the project workspace

The engineer reads the latest block, implements the assigned task, then appends a `STATUS: review_required` block.

### 5. Repeat (Manual only)

Switch back to the architect, give it the updated `handoff.md`. Continue until the architect writes `STATUS: plan_complete`.

---

## Programmatic API

All code must be run from the `coordination/` directory.

### Parse a handoff block

```python
from src.handoff_parser import parse_block

block_text = """
ROLE: architect
STATUS: continue
NEXT: engineer
TASK_ID: task-001
TITLE: Build the parser
SUMMARY: Implement parse_block and extract_latest.
ACCEPTANCE:
- valid block returns HandoffMessage
- missing field returns errors
CONSTRAINTS:
- stdlib only
FILES_TO_TOUCH:
- src/handoff_parser.py
CHANGED_FILES:
- n/a
VALIDATION:
- n/a
BLOCKERS:
- none
"""

msg, errors = parse_block(block_text)
if msg:
    print(msg.role.value, msg.next.value, msg.task_id)
else:
    print("Parse failed:", errors)
```

### Extract the latest block from a file

```python
from src.handoff_parser import extract_latest

content = open("handoff.md").read()
msg, errors = extract_latest(content)
if msg:
    print("Next actor:", msg.next.value)
    print("Status:", msg.status.value)
```

### Manage tasks

```python
from src.task_store import TaskStore
from src.models import TaskStatus

store = TaskStore("tasks.json")

# List all tasks
for task in store.all():
    print(task.id, task.status.value)

# Advance a task through the lifecycle
store.update_status("task-001", TaskStatus.IN_ENGINEERING)
store.update_status("task-001", TaskStatus.READY_FOR_ARCHITECT_REVIEW)
store.update_status("task-001", TaskStatus.DONE)

# Only one task can be in_engineering at a time
# store.update_status("task-002", TaskStatus.IN_ENGINEERING)  # raises ValueError if task-001 is active
```

Valid state transitions:

```
planned → ready_for_engineering → in_engineering → ready_for_architect_review → done
                                       ↕                        ↕
                                 rework_requested ──────────────┘
                                       ↕
                              (any state) → blocked → in_engineering
```

### Check workflow routing logic

```python
from src.models import AgentRole, HandoffStatus, NextActor, HandoffMessage
from src.workflow import get_next_actor, is_plan_complete, is_blocked, is_human_escalation

msg = HandoffMessage(
    role=AgentRole.ENGINEER,
    status=HandoffStatus.REVIEW_REQUIRED,
    next=NextActor.ARCHITECT,
    task_id="task-001",
    title="Done",
    summary="Implemented X.",
)

print(get_next_actor(msg).value)    # "architect"
print(is_plan_complete(msg))        # False
print(is_blocked(msg))              # False
```

---

## Handoff Block Format

Every agent turn must end with a structured block. See `docs/protocol.md` for the full spec.

```
---HANDOFF---
ROLE: architect | engineer
STATUS: continue | approved | rework_required | review_required | blocked | needs_human | plan_complete
NEXT: architect | engineer | human | none
TASK_ID: task-NNN
TITLE: Short task label
SUMMARY: One-paragraph explanation
ACCEPTANCE:
- criterion one
- criterion two
CONSTRAINTS:
- constraint one
FILES_TO_TOUCH:
- src/foo.py          ← architect uses this
CHANGED_FILES:
- src/foo.py          ← engineer uses this
VALIDATION:
- test result
BLOCKERS:
- none
---END---
```

---

## Role Summary

| Responsibility | Architect | Engineer |
|---|---|---|
| Planning and task decomposition | ✅ | ❌ |
| Writing production code | ❌ | ✅ |
| Defining acceptance criteria | ✅ | ❌ |
| Running validation | ❌ | ✅ |
| Reviewing completed work | ✅ | ❌ |
| Declaring completion (`plan_complete`) | ✅ | ❌ |

---

## Human Intervention

At any point you can:
- Edit `handoff.md` to correct a bad block (note the edit with a comment)
- Edit `tasks.json` directly to fix task status
- Override the next actor by appending a new block with `ROLE: architect` or `ROLE: engineer`
- Stop the workflow by leaving the `NEXT: human` state unresolved

The workflow resumes from the latest valid `---HANDOFF---` block whenever either agent is restarted.

---

## Further Reading

- `docs/protocol.md` — complete handoff block specification
- `docs/workflow.md` — 10-step loop, lifecycle diagrams, session instructions
- `prompts/shared_rules.md` — the 10 rules both agents must follow
