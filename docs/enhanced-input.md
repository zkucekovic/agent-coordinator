# Enhanced Input Features

The coordinator now uses **readline-enhanced input** for the best user experience with full shell-like editing capabilities.

## Features

### Keyboard Shortcuts

All input prompts support these standard shell shortcuts:

| Shortcut | Action |
|----------|--------|
| **Ctrl+A** | Move cursor to beginning of line |
| **Ctrl+E** | Move cursor to end of line |
| **Ctrl+K** | Kill (cut) from cursor to end of line |
| **Ctrl+W** | Delete word backward |
| **Ctrl+U** | Delete from cursor to beginning of line |
| **Ctrl+D** | Delete character under cursor |
| **Arrow Left/Right** | Move cursor one character |
| **Arrow Up/Down** | Navigate command history |
| **Tab** | Auto-completion (for choices) |
| **Ctrl+L** | Clear screen |

### Command History

- All inputs are saved to `~/.agent_coordinator_history`
- Use **Up/Down** arrows to recall previous inputs
- History persists across sessions
- Maximum 1000 entries

### Tab Completion

When choosing from a menu (like the interrupt menu), you can:
- Type partial text
- Press **Tab** to see completions
- Press **Tab** again to cycle through options

Example:
```
Choice [c/r/e/m/i/q]: co<Tab>
→ Completes to "continue"
```

### Color Support

Prompts and messages are color-coded (if terminal supports it):
- **Cyan** - Prompts
- **Green** - Success messages
- **Red** - Error messages
- **Yellow** - Warnings
- **Blue** - Info messages

Colors can be disabled with `NO_COLOR=1` environment variable.

## Where It's Used

### 1. Interrupt Menu (Ctrl+C)

```
Choice [c/r/e/m/i/q]: <cursor here>
```

Features:
- Tab completion for choices
- Command history
- All editing shortcuts
- Invalid inputs re-prompt

### 2. Human Input Prompt

```
Choice [e/m/v/c/q]: <cursor here>
```

Same features as interrupt menu.

### 3. Task Creation (Fallback Mode)

```
Task ID (e.g., task-001): <cursor here>
Title: <cursor here>
Description: <cursor here>
Acceptance criteria (one per line):
  - <cursor here>
```

Each line supports full editing capabilities.

### 4. Multi-line Input

```
Enter message (empty line to finish):
> First line<cursor here>
> Second line with editing
> <empty line to finish>
```

Each line can be edited independently with all shortcuts.

## Examples

### Basic Editing

```
Choice [c/r/e/m/i/q]: continue<Ctrl+W>quit
→ Deletes "continue", types "quit"

Task ID: task-001-authentication<Ctrl+U>task-999
→ Deletes whole line, types new ID
```

### Using History

```
Choice: continue<Enter>
# Later...
Choice: <Up>
→ Shows "continue" again
```

### Tab Completion

```
Choice [c/r/e/m/i/q]: con<Tab>
→ Completes to "continue"

Choice [c/r/e/m/i/q]: e<Tab>
→ Completes to "edit"
```

## Technical Details

### Implementation

Uses Python's `readline` module which provides:
- Line editing
- History management
- Tab completion
- Signal handling

### Compatibility

- **Works**: macOS, Linux, BSD
- **Limited**: Windows (use WSL for best experience)
- **Fallback**: If readline unavailable, falls back to basic `input()`

### History File

Location: `~/.agent_coordinator_history`

Format:
```
continue
quit
task-001
...
```

Manual management:
```bash
# View history
cat ~/.agent_coordinator_history

# Clear history
rm ~/.agent_coordinator_history

# Disable history
export HISTFILE=/dev/null
```

## Configuration

### Vi Mode (Optional)

To use vi-style editing instead of Emacs (default):

Edit `agent_coordinator/infrastructure/enhanced_input.py`:
```python
# Uncomment this line
readline.parse_and_bind("set editing-mode vi")
```

Then:
- **Esc** enters command mode
- **i** enters insert mode
- **h/j/k/l** for navigation
- All vi commands work

### Disable Colors

```bash
# Disable for single run
NO_COLOR=1 agent-coordinator --workspace .

# Disable globally
export NO_COLOR=1
```

### Disable History

```bash
# Set history to /dev/null
agent-coordinator --workspace .
# Then manually set in code or use environment
```

## Comparison

### Before (Basic Input)

```
Choice [c/r/e/m/i/q]: continu
# Typo! Have to delete each char
# <Backspace><Backspace><Backspace><Backspace><Backspace><Backspace><Backspace>
# Type again...
```

### After (Enhanced Input)

```
Choice [c/r/e/m/i/q]: continu<Ctrl+W>continue
# Fixed with one shortcut!

# Or use history:
Choice [c/r/e/m/i/q]: <Up>
# Previous command appears!

# Or tab completion:
Choice [c/r/e/m/i/q]: con<Tab>
# Completes to "continue"!
```

## Benefits

### For Users

- **Faster editing**: Fix mistakes quickly with shortcuts
- **Less retyping**: Command history recalls previous inputs
- **Fewer errors**: Tab completion prevents typos
- **Better UX**: Familiar shell experience

### For Development

- **Testing**: Quickly re-enter test values
- **Debugging**: Recall previous commands
- **Efficiency**: Edit long inputs easily

## Tips

### Power User Shortcuts

```bash
# Fix typo at start of line
Ctrl+A, type correction, Ctrl+E to continue

# Delete entire line and start over
Ctrl+U

# Delete last word
Ctrl+W

# Recall and edit previous command
Up, Ctrl+A, make changes, Enter
```

### Tab Completion Tricks

```bash
# See all options
Choice [c/r/e/m/i/q]: <Tab><Tab>
→ Shows: continue, retry, edit, message, inspect, quit

# Complete partial match
Choice: co<Tab>
→ continue

Choice: e<Tab>
→ edit
```

### History Tricks

```bash
# Scroll through history
Up, Up, Up, Down, Down

# Search history (if readline configured)
Ctrl+R, type search term
```

## Future Enhancements

Potential additions:
- Custom completion for task IDs
- Custom completion for file paths
- Multi-line editing with history
- Configurable keybindings
- Syntax highlighting in prompts

## Demo

Try it yourself:

```bash
cd /Users/zkucekovic/Projects/Privatno/agent-coordinator
python3 examples/demo_enhanced_input.py
```

This interactive demo lets you test:
1. Basic enhanced input
2. Tab completion
3. Multi-line editing
4. All keyboard shortcuts

The enhanced input makes the coordinator feel like a native shell application with full editing capabilities!
