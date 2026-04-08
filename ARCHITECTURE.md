# Agent Coordinator Architecture

## Design Philosophy

Agent Coordinator follows **hexagonal architecture** (ports and adapters) with strict separation between domain logic, application services, and infrastructure concerns. The core principle: **coordination protocol is backend-agnostic and human-readable**.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│ CLI (agent_coordinator/cli.py)                          │
│ - Argument parsing                                       │
│ - Orchestration loop                                     │
│ - Interactive control (Ctrl+C)                          │
│ - TUI output                                            │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│ APPLICATION LAYER (agent_coordinator/application/)                    │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ WorkflowRouter                                      │ │
│ │ - Read latest handoff block                        │ │
│ │ - Determine next agent from NEXT field             │ │
│ │ - Dispatch to agent runner                         │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ TaskService                                         │ │
│ │ - Sync tasks.json with handoff events              │ │
│ │ - Transition task state based on STATUS            │ │
│ │ - Track rework cycles                              │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ PromptBuilder                                       │ │
│ │ - Load agent prompt from prompts/{role}.md         │ │
│ │ - Inject AGENTS.md, SPECIFICATION.md, plan.md      │ │
│ │ - Inject shared_rules.md                           │ │
│ │ - Inject handoff.md content                        │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ AgentRunner (interface)                            │ │
│ │ - Abstract backend execution                       │ │
│ │ - Returns RunResult(session_id, text)              │ │
│ └────────────────────────────────────────────────────┘ │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│ DOMAIN LAYER (agent_coordinator/domain/)                              │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Models (handoff_block.py, task.py)                 │ │
│ │ - HandoffBlock: structured message between agents  │ │
│ │ - Task: work item with state machine               │ │
│ │ - RunResult: backend execution result              │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ TaskLifecycle                                       │ │
│ │ - State machine: planned → in_engineering → done   │ │
│ │ - Transition rules based on handoff STATUS         │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ RetryPolicy                                         │ │
│ │ - max_rework limit                                 │ │
│ │ - Escalation strategy (needs_human, blocked)       │ │
│ └────────────────────────────────────────────────────┘ │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│ INFRASTRUCTURE LAYER (agent_coordinator/infrastructure/)              │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ Runners (runners/)                                  │ │
│ │ - OpencodeRunner: calls `opencode` CLI             │ │
│ │ - ClaudeRunner: calls `claude` CLI                 │ │
│ │ - CopilotRunner: calls `gh copilot` CLI            │ │
│ │ - ManualRunner: prompts human for input            │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ FileStore                                           │ │
│ │ - Read/write handoff.md                            │ │
│ │ - Read/write tasks.json                            │ │
│ │ - Append to .agent-coordinator/events.jsonl         │ │
│ │ - Manage .agent-coordinator/sessions.json          │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌────────────────────────────────────────────────────┐ │
│ │ HandoffParser                                       │ │
│ │ - Extract blocks from handoff.md                   │ │
│ │ - Validate required fields                         │ │
│ │ - Parse status, next agent, task ID                │ │
│ └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## Key Design Patterns

### 1. Hexagonal Architecture (Ports & Adapters)

**Domain Layer** contains business logic with no dependencies:
- Task state machine
- Retry policy rules
- Data models (HandoffBlock, Task)

**Application Layer** orchestrates domain logic:
- Routing decisions (WorkflowRouter)
- Task synchronization (TaskService)
- Prompt construction (PromptBuilder)

**Infrastructure Layer** handles I/O and external systems:
- Backend CLI execution (runners)
- File read/write (FileStore)
- Protocol parsing (HandoffParser)

**Benefit**: Domain logic is testable without I/O. Backends are swappable without changing domain or application layers.

### 2. Strategy Pattern (AgentRunner)

`AgentRunner` interface allows pluggable backends:

```python
class AgentRunner:
    def run(self, message: str, workspace: str, 
            session_id: str, model: str) -> RunResult:
        pass
```

Implementations:
- `OpencodeRunner`: calls `opencode workspace {message}`
- `ClaudeRunner`: calls `claude session {session_id} {message}`
- `CopilotRunner`: calls `gh copilot --workspace {workspace}`
- `ManualRunner`: prompts user and waits for handoff edit

**Benefit**: Add new backends without modifying coordinator logic. Users can implement custom runners for proprietary tools.

### 3. Template Method (PromptBuilder)

Prompt construction follows fixed structure:

```
1. Agent role instructions (prompts/{role}.md)
2. Project rules (AGENTS.md) — optional
3. Specification (SPECIFICATION.md) — optional
4. Implementation plan (plan.md) — optional
5. Shared protocol rules (prompts/shared_rules.md)
6. Current handoff state (handoff.md)
```

**Benefit**: Consistent prompt structure across all agents. Easy to extend with new injection points.

### 4. State Machine (TaskLifecycle)

Tasks follow deterministic state transitions:

```
planned
  ↓ (task assigned)
ready_for_engineering
  ↓ (agent picks up task)
in_engineering
  ↓ (STATUS: review_required)
ready_for_architect_review
  ↓ (STATUS: approved)
done

Rework loop:
ready_for_architect_review → rework_requested → in_engineering
```

**Benefit**: Task status always reflects current workflow state. Rework cycles are tracked for escalation policy.

### 5. Event Sourcing (.agent-coordinator/events.jsonl)

Every agent turn is logged as an immutable event:

```json
{
  "timestamp": "2026-04-07T09:30:00Z",
  "agent_role": "developer",
  "session_id": "abc123",
  "status": "review_required",
  "next_agent": "architect",
  "changed_files": ["src/auth.py"],
  "task_id": "task-001"
}
```

**Benefit**: Full audit trail. Can replay workflow history. Debug state transitions.

## Data Flow

### Agent Turn Execution

```
1. CLI reads latest handoff block from handoff.md
2. WorkflowRouter extracts NEXT field → determines next agent
3. PromptBuilder constructs prompt for that agent
4. AgentRunner executes backend CLI with prompt
5. Backend LLM generates response (ideally appends to handoff.md)
6. CLI verifies handoff.md was updated
7. TaskService syncs tasks.json based on new STATUS
8. CLI appends event to .agent-coordinator/events.jsonl
9. Loop continues with step 1
```

### Retry Logic

```
If handoff.md not updated after agent turn:
  1. Check if max retries exceeded → escalate to needs_human
  2. Re-run same agent with "You forgot to update handoff.md" reminder
  3. Increment retry counter

If task exceeds max_rework cycles:
  1. Set STATUS: needs_human
  2. Pause workflow
  3. Wait for human intervention
```

## File Structure

```
agent-coordinator/
├── agent_coordinator/
│   ├── cli.py                    # Entry point, orchestration loop
│   ├── domain/                   # Pure data models, state machine, retry policy
│   ├── application/              # Router, TaskService, PromptBuilder, AgentRunner
│   ├── infrastructure/           # Runners, file I/O, TUI, event log
│   ├── handoff_parser.py         # Regex-based parser for handoff blocks
│   ├── prompts/                  # Agent instructions (shipped with package)
│   │   ├── architect.md
│   │   ├── developer.md
│   │   ├── qa_engineer.md
│   │   ├── shared_rules.md       # Protocol rules for all agents
│   │   └── agent_template.md     # Template for new roles
│   └── helpers/                  # Helper scripts (task creator, etc.)
├── tests/
│   ├── test_*.py                 # Unit tests (188 tests, no I/O)
│   └── integration/              # Integration tests (real backends)
├── examples/
│   └── tetris-demo/              # End-to-end demo workflow
├── docs/
│   ├── protocol.md               # Handoff block specification
│   ├── workflow.md               # Coordinator loop details
│   ├── custom-backends.md        # How to add backends
│   └── interactive-control.md    # Ctrl+C menu usage
├── agents.json                   # Default agent configuration
├── pyproject.toml                # Package metadata
└── README.md                     # User documentation
```

## Extension Points

### 1. Add Custom Backend

Implement `AgentRunner` interface:

```python
from agent_coordinator.application.runner import AgentRunner
from agent_coordinator.domain.models import RunResult

class MyRunner(AgentRunner):
    def run(self, message, workspace, session_id=None, model=None):
        # Call your custom CLI tool
        result = subprocess.run(
            ["my-tool", "--input", message],
            cwd=workspace, capture_output=True, text=True
        )
        return RunResult(session_id=session_id, text=result.stdout)
```

Register in `cli.py` runner factory:

```python
def create_runner(backend_name, config):
    if backend_name == "my_tool":
        return MyRunner()
    # ... existing backends
```

Reference in `agents.json`:

```json
{
  "agents": {
    "my_agent": {
      "backend": "my_tool",
      "prompt_file": "prompts/my_agent.md"
    }
  }
}
```

### 2. Add Custom Agent Role

1. Create `prompts/my_role.md` with instructions
2. Add to `agents.json`:

```json
{
  "agents": {
    "my_role": {
      "backend": "opencode",
      "prompt_file": "prompts/my_role.md"
    }
  }
}
```

3. Update other prompts to route to it (set `NEXT: my_role`)

### 3. Project-Specific Rules

Create `AGENTS.md` in workspace:

```markdown
## Coding Standards
- Use type hints
- Write docstrings
- No print() statements in production code
```

PromptBuilder automatically injects this into all agent prompts.

### 4. Custom Event Handlers

Modify `cli.py` orchestration loop to subscribe to events:

```python
def on_task_complete(task_id, status):
    # Send notification
    # Update external tracker
    # Trigger deployment
    pass
```

## Testing Strategy

### Unit Tests (tests/test_*.py)

- **Domain layer**: Test state machines, retry policy, validation rules
- **Application layer**: Test routing logic, task sync, prompt construction (mock I/O)
- **Infrastructure layer**: Test parsing, file ops (use temp files)
- **Coverage**: 188 tests, runs in <1 second, no external dependencies

### Integration Tests (tests/integration/)

- **End-to-end**: Real backend API calls (requires API tokens)
- **Gated**: Set `RUN_INTEGRATION_TESTS=1` to enable
- **Validates**: Prompt format, session persistence, handoff parsing

### Demo (examples/tetris-demo/)

- **Purpose**: User-facing validation of full workflow
- **Runs**: Architect → Developer → QA loop for building Tetris game
- **Validates**: Multi-turn coordination, task decomposition, human readability

## Security Considerations

### Trust Model

- **Filesystem trust**: All agents share workspace, can read/write any file
- **No sandboxing**: Agents execute code via backend CLIs (opencode, claude run arbitrary code)
- **Human oversight**: Ctrl+C control and handoff.md visibility provide safety

### Threat Mitigation

- **Append-only handoff.md**: Agents can't rewrite history
- **Session isolation**: Each agent has separate session ID
- **Audit trail**: .agent-coordinator/events.jsonl logs all actions
- **Human escalation**: needs_human status forces review

### Secrets Management

- **Backend API keys**: Stored by backend CLIs (gh, opencode, claude), not by coordinator
- **No secrets in code**: Coordinator never handles credentials
- **Git-ignored**: .agent-coordinator/ directory added to .gitignore

## Performance Characteristics

- **Latency**: Dominated by LLM API calls (10-60s per turn)
- **Throughput**: Sequential turn-based (1 agent at a time)
- **Memory**: Minimal (loads handoff.md, tasks.json into memory ~1MB)
- **Disk I/O**: Append-only writes, no database overhead
- **Scalability**: Tested to 30+ turn workflows without issues

## Future Enhancements (Not in Current Version)

- **Parallel agent execution**: Run independent tasks concurrently
- **A2A protocol integration**: Dispatch to remote agents via HTTP
- **GUI/TUI**: Interactive workflow visualization
- **Rollback**: Revert to previous handoff state
- **Multi-workspace**: Coordinate agents across multiple projects
