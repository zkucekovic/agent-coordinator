# Editor Integration Guide

The agent coordinator integrates with your preferred text editor for human-friendly editing of specifications, tasks, and handoff messages.

## Editor Detection

The coordinator uses standard Unix environment variables:

1. `$VISUAL` - Your preferred visual editor
2. `$EDITOR` - Your fallback editor
3. Default: `vi` if neither is set

### Setting Your Editor

```bash
# In your .bashrc or .zshrc
export EDITOR=vim
export VISUAL=code  # or code --wait for VS Code

# Or set for a single session
EDITOR=nano python -m agent_coordinator.helpers task --workspace ./project
```

### Common Editors

```bash
export EDITOR=vim       # Vim
export EDITOR=nvim      # Neovim
export EDITOR=emacs     # Emacs
export EDITOR=nano      # Nano
export EDITOR="code --wait"   # VS Code (--wait is important!)
export EDITOR="subl -w"       # Sublime Text
export EDITOR="atom --wait"   # Atom
```

**Important:** For GUI editors, use the `--wait` flag so the tool waits for you to close the file.

## Creating Tasks with Editor

### Command

```bash
python -m agent_coordinator.helpers task --workspace ./project
```

### Editor Template

When you run the command, your editor opens with:

```markdown
# Edit the task below
# First line format: task-id: Task Title
# Lines starting with # will be ignored
# Save and close when done

task-001: Implement user authentication

Build a JWT-based authentication system.
Users should be able to log in and log out.
Tokens should expire after 1 hour.

## Acceptance Criteria

- POST /auth/login endpoint implemented
- POST /auth/logout endpoint implemented
- JWT tokens generated correctly
- Tokens expire after 1 hour
- Unit tests pass

## Dependencies

- task-000
```

### Workflow

1. Command opens editor
2. Edit the template
3. Save and close
4. Tool parses the content
5. Creates/updates tasks.json
6. Creates handoff.md
7. Shows next steps

### Benefits

- **Natural editing**: Use your familiar editor
- **Syntax highlighting**: Markdown support
- **Copy/paste**: Easy from other documents
- **Multi-line**: No awkward prompts
- **Templates**: Structure is clear

## Creating Specifications with Editor

### Command

```bash
python -m agent_coordinator.helpers spec --workspace ./project
```

### Editor Template

```markdown
# Edit the specification below
# Lines starting with # will be ignored
# Save and close the editor when done

User Authentication System

## Description

Implement a complete authentication system using JWT tokens.
The system should support login, logout, and token refresh.
All endpoints must validate inputs and return appropriate errors.

## Requirements

- POST /auth/login accepts email and password
- POST /auth/logout invalidates tokens
- POST /auth/refresh issues new tokens
- All endpoints validate input
- Proper error codes for all cases
- Unit tests with >80% coverage

## Constraints

- Use stdlib jwt module only
- No new dependencies
- Tokens expire after 1 hour
- Follow existing code style
```

### Workflow

Same as tasks - edit, save, close, and the tool handles the rest.

## Adding Messages via Ctrl+C Menu

When you press Ctrl+C during execution and choose 'm':

### With Editor (Default)

```markdown
# Edit your handoff message below
# This will be added to handoff.md
# Lines starting with # will be ignored
#
# Current handoff context:
# ==================================================
# ROLE: developer
# STATUS: continue
# TASK_ID: task-001
# ==================================================

Write your message or guidance here...

You can provide:
- Additional context for the agent
- Corrections or clarifications
- Specific instructions
- Questions or concerns
```

### Without Editor

If editor fails or unavailable, fallback to prompts:
```
Enter message (empty line to finish):
> Line 1
> Line 2
>
```

## Editing Handoff Directly

When you press Ctrl+C and choose 'e', the handoff.md file opens directly in your editor:

- View the complete handoff structure
- Make surgical edits
- Fix agent mistakes
- Add comments
- Modify any section

**Saves immediately** when you close the editor.

## Command Options

### Task Creation

```bash
python -m agent_coordinator.helpers task --workspace PATH [OPTIONS]

Options:
  --no-editor      Use prompts instead of opening editor
  --no-handoff     Don't create initial handoff.md
```

### Specification Creation

```bash
python -m agent_coordinator.helpers spec --workspace PATH [OPTIONS]

Options:
  --filename FILE  Specification filename (default: SPECIFICATION.md)
  --no-editor      Use prompts instead of opening editor
  --no-handoff     Don't create initial handoff.md
```

## Editor Integration Benefits

### For Users

- **Familiar interface**: Use your preferred editor
- **Faster editing**: No clunky prompts
- **Better formatting**: See structure clearly
- **Syntax support**: Markdown highlighting
- **Easy corrections**: Delete, copy, paste freely

### For Teams

- **Consistency**: Templates enforce structure
- **Lower friction**: Natural editing experience
- **Better quality**: Easier to write comprehensive specs
- **Version control**: All in text files

## Troubleshooting

### Editor Not Opening

```bash
# Check your environment
echo $EDITOR
echo $VISUAL

# Set explicitly
export EDITOR=vim
python -m agent_coordinator.helpers task --workspace ./project
```

### Editor Closes Immediately (GUI Editors)

For GUI editors, use the wait flag:

```bash
export EDITOR="code --wait"    # VS Code
export EDITOR="subl -w"        # Sublime
export EDITOR="atom --wait"    # Atom
```

### Permission Denied

Ensure your editor is executable:
```bash
which vim  # Should show path
chmod +x /path/to/editor  # If needed
```

### Prefer Prompts

Use `--no-editor` to skip the editor:
```bash
python -m agent_coordinator.helpers task --workspace ./project --no-editor
```

## Environment Variables

```bash
# Set your preferred editor
export VISUAL=nvim      # Used first if set
export EDITOR=vim       # Used if VISUAL not set

# For this session only
EDITOR=nano python -m agent_coordinator.helpers spec --workspace ./project
```

## Examples

### Create Task with Vim

```bash
export EDITOR=vim
python -m agent_coordinator.helpers task --workspace ./my-feature

# Vim opens with template
# Edit, :wq to save
# Task created
```

### Create Spec with VS Code

```bash
export EDITOR="code --wait"
python -m agent_coordinator.helpers spec --workspace ./my-feature

# VS Code opens with template
# Edit, close tab
# Specification created
```

### Edit Handoff During Execution

```bash
agent-coordinator --workspace ./project

# During execution, press Ctrl+C
# Choose 'e' from menu
# Handoff opens in editor
# Edit, save, close
# Execution continues with your changes
```

## Advanced Usage

### Custom Templates

You can modify the templates in:
- `agent_coordinator/infrastructure/editor.py`

### Editor Configuration

The editor integration respects your editor's configuration:
- `.vimrc` for Vim
- `settings.json` for VS Code
- `.emacs` for Emacs
- etc.

### Syntax Highlighting

For best experience, ensure Markdown syntax highlighting is enabled in your editor.

## Integration with Workflow

### Typical Workflow

1. **Create spec**: `python -m agent_coordinator.helpers spec --workspace ./project`
   - Opens editor with template
   - Fill in details
   - Save and close

2. **Run coordinator**: `agent-coordinator --workspace ./project`
   - Agents start working

3. **Interrupt if needed**: Press Ctrl+C
   - Choose 'e' to edit handoff directly
   - Choose 'm' to add guidance
   - Choose 'i' to inspect

4. **Continue**: Let agents finish

### No More Hand-Editing JSON

Before: Edit `tasks.json` by hand (error-prone)
After: Use editor with templates (guided, validated)

### Natural Multi-line Input

Before: Awkward prompts for each line
After: Familiar editor experience

The editor integration makes human interaction with the coordinator feel natural and efficient!
