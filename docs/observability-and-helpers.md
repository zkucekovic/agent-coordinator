# Enhanced Observability and Task Creation

This document describes the new features for making agent work more observable and task/specification creation easier.

## Enhanced Agent Output Display

The coordinator now features an enhanced output display that reserves screen space for real-time agent output.

### Features

- **Animated Thinking Indicator**: Spinning cursor shows agent is actively working
- **Real-time Output**: See agent responses as they're generated (for streaming backends)
- **Clean Headers**: Clear agent identification with backend, task, and status
- **Status Summaries**: Success/failure indicators with next steps
- **TTY Detection**: Automatically falls back to simple output in non-interactive environments

### Visual Example

While agent is working:
```
════════════════════════════════════════════════════════════════════
🤖 Agent: ARCHITECT
   Backend: copilot
   Task: task-001
   Status: continue
────────────────────────────────────────────────────────────────────

⠹ architect is thinking...
```

Once output starts streaming:
```
Analyzing the specification...
Creating implementation plan...
Breaking down into tasks...
Updating handoff.md...

────────────────────────────────────────────────────────────────────
✅ Turn completed successfully
   New status: review_required
   Next agent: qa_engineer
════════════════════════════════════════════════════════════════════
```

### Usage

The enhanced display is automatically enabled when running in a TTY:

```bash
agent-coordinator --workspace /path/to/project
```

To force simple output (no reserved lines):

```bash
agent-coordinator --workspace /path/to/project --quiet
```

## Easy Task and Specification Creation

New helper commands make it easy for humans to create tasks and specifications **using your preferred text editor**.

### Create a Task

```bash
python -m agent_coordinator.helpers task --workspace /path/to/workspace
```

This opens your text editor (configured via `$EDITOR` or `$VISUAL`) with a template:

```markdown
# Edit the task below
# First line format: task-id: Task Title
# Lines starting with # will be ignored
# Save and close when done

task-001: Task Title Here

Description of the task...
Can be multiple lines.

## Acceptance Criteria

- Criterion 1
- Criterion 2
- Criterion 3

## Dependencies

- task-000
```

**Benefits:**
- Edit in your familiar editor (vim, emacs, vscode, etc.)
- Syntax highlighting
- Multi-line editing is natural
- Copy/paste easily
- No awkward prompts

**Fallback:** Use `--no-editor` for prompt-based input if needed.

### Create a Specification

```bash
python -m agent_coordinator.helpers spec --workspace /path/to/workspace
```

Opens your editor with a specification template:

```markdown
# Edit the specification below
# Lines starting with # will be ignored
# Save and close the editor when done

Specification Title Here

## Description

Write your description here...
Multiple lines are fine.

## Requirements

- Requirement 1
- Requirement 2
- Requirement 3

## Constraints

- Constraint 1
- Constraint 2
```

The tool will:
1. Open your preferred editor
2. Parse the structured content
3. Create SPECIFICATION.md
4. Create initial handoff.md (optional)
5. Show next steps

### Example: Creating a Task

```bash
$ python -m agent_coordinator.helpers task --workspace ./my-feature

=== Create New Task ===

Task ID (e.g., task-001): task-001
Title: Add user authentication
Description: Implement JWT-based authentication

Acceptance criteria (one per line, empty line to finish):
  - POST /auth/login endpoint works
  - JWT tokens are issued correctly
  - Tokens expire after 1 hour
  - Unit tests pass
  - 

Dependencies (task IDs, one per line, empty line to finish):
  - 

✅  Task 'task-001' added to ./my-feature/tasks.json
✅  Initial handoff created at ./my-feature/handoff.md

✨ Task creation complete!

Next steps:
  1. Review the task in ./my-feature/tasks.json
  2. Run: agent-coordinator --workspace ./my-feature
```

### Example: Creating a Specification

```bash
$ python -m agent_coordinator.helpers spec --workspace ./my-feature

=== Create New Specification ===

Title: User Authentication System

Description (multiple lines, type END on a line by itself when done):
Build a JWT-based authentication system for the API.
Users should be able to log in, log out, and refresh tokens.
All endpoints must validate tokens on protected routes.
END

Requirements (one per line, empty line to finish):
  - POST /auth/login accepts email and password
  - POST /auth/logout invalidates tokens
  - POST /auth/refresh issues new tokens
  - All endpoints return proper error codes
  - Unit tests with >80% coverage
  -

Constraints (one per line, empty line to finish):
  - Use stdlib jwt module only
  - Tokens expire after 1 hour
  - No new dependencies
  -

✅  Specification written to ./my-feature/SPECIFICATION.md
✅  Initial handoff created at ./my-feature/handoff.md

✨ Specification creation complete!

Next steps:
  1. Review the specification in ./my-feature/SPECIFICATION.md
  2. Run: agent-coordinator --workspace ./my-feature
```

## Command Reference

### Task Creation

```bash
python -m agent_coordinator.helpers task --workspace PATH [--no-handoff]
```

Options:
- `--workspace PATH`: Workspace directory (required)
- `--no-handoff`: Don't create initial handoff.md

### Specification Creation

```bash
python -m agent_coordinator.helpers spec --workspace PATH [--filename FILE] [--no-handoff]
```

Options:
- `--workspace PATH`: Workspace directory (required)
- `--filename FILE`: Specification filename (default: SPECIFICATION.md)
- `--no-handoff`: Don't create initial handoff.md

## Technical Details

### Output Display Implementation

The enhanced display uses ANSI escape codes to manage cursor position:
- `\033[{n}A` - Move cursor up n lines
- `\033[{n}B` - Move cursor down n lines  
- `\033[2K` - Clear current line

It automatically detects TTY capability using `sys.stdout.isatty()` and falls back to simple streaming output in non-TTY environments (pipes, redirects, CI/CD).

### Runner Integration

All runners now support an optional `on_output` callback:

```python
def run(
    self,
    message: str,
    workspace: Path,
    session_id: str | None = None,
    model: str | None = None,
    on_output: Callable[[str], None] | None = None,  # NEW
) -> RunResult:
```

When provided, runners call this callback with output chunks for real-time display.

### Backwards Compatibility

All new features are backwards compatible:
- Existing runners work without modification
- `on_output` parameter is optional
- Display automatically adapts to environment
- Helper commands are separate utilities

## Benefits

### For Developers

- **Better Visibility**: See what agents are doing in real-time
- **Faster Debugging**: Spot issues as they happen
- **Easier Setup**: Create tasks/specs without hand-editing JSON

### For Teams

- **Consistent Format**: Helper tools enforce structure
- **Lower Barrier**: Non-technical users can create tasks
- **Better Documentation**: Specifications follow templates

## Future Enhancements

Potential improvements:
- Progress bars for long-running operations
- Color-coded output by agent type
- Configurable number of reserved lines
- Export to different specification formats
- Task templates for common patterns
