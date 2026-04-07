# Agent Output Window

The coordinator displays a **live output window** showing the last N lines of agent activity in real-time.

## Overview

```
═══════════════════════════════════════════════════════════════════
AGENT: ARCHITECT
Backend: copilot | Task: task-001 | Status: continue
────────────────────────────────────────────────────────────────────

[⠹] architect working

┌─────────────────────────────────────────────────────────────────┐
│ 💭 architect thinking...                                        │
├─────────────────────────────────────────────────────────────────┤
│ Analyzing the requirements...                                   │
│ Breaking down into smaller tasks                                │
│ Task 1: Setup authentication system                             │
│ Task 2: Create user database schema                             │
│ Task 3: Implement JWT token handling                            │
│ Task 4: Add password hashing with bcrypt                        │
│ Task 5: Setup OAuth providers                                   │
│ Reviewing security considerations                               │
│ Checking compliance requirements                                │
│ Planning implementation sequence                                │
└─────────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────────
[OK] Status: continue | Next: developer
═══════════════════════════════════════════════════════════════════
```

## Features

### 1. Scrolling Window

- Shows **last 10 lines** by default (configurable)
- Automatically scrolls as new output arrives
- Truncates long lines to fit terminal width
- Updates in real-time as agent produces output

### 2. Visual Indicators

- **💭 thinking...** - Header shows agent is active
- **Box borders** - Clean visual separation
- **Animated cursor** - Thinking indicator before output

### 3. Smart Display

- **TTY mode**: Live scrolling window with ANSI codes
- **Non-TTY mode**: Simple line-by-line output (pipes, logs)
- **Automatic adaptation**: Detects terminal capabilities

## Configuration

### Command Line

```bash
# Default: 10 lines
agent-coordinator --workspace .

# Show 15 lines
agent-coordinator --workspace . --output-lines 15

# Show 5 lines (compact)
agent-coordinator --workspace . --output-lines 5

# Show 20 lines (verbose)
agent-coordinator --workspace . --output-lines 20
```

### Valid Range

- **Minimum**: 3 lines (still useful)
- **Maximum**: 50 lines (practical limit)
- **Default**: 10 lines (balanced)
- **Recommended**: 10-15 lines for most workflows

## Use Cases

### 1. Monitor Progress

Watch agent thinking process:
- "Analyzing requirements..."
- "Breaking down tasks..."
- "Creating implementation plan..."

### 2. Debug Issues

See what agent is doing when stuck:
- Which step is taking long?
- What's the last output?
- Is it making progress?

### 3. Transparency

Human observer can see:
- Agent's reasoning process
- What it's considering
- Decision-making steps

### 4. Catch Errors Early

Notice problems immediately:
- "Error: file not found"
- "Warning: deprecated API"
- "Failed to compile"

## Output Sources

Different backends provide different levels of output:

### Copilot Backend
```
Reading workspace files...
Analyzing handoff.md...
Generating response...
Writing handoff.md...
```

### Claude Backend
```
<thinking>
Let me analyze the requirements...
I'll break this into subtasks...
</thinking>

Creating implementation plan...
```

### Custom Backends

Any text output to stdout is captured and displayed.

## Window Behavior

### Initial State

```
┌──────────────────────────────────────┐
│ 💭 architect thinking...             │
├──────────────────────────────────────┤
│                                      │  ← Empty lines
│                                      │
│                                      │
└──────────────────────────────────────┘
```

### As Output Arrives

```
┌──────────────────────────────────────┐
│ 💭 architect thinking...             │
├──────────────────────────────────────┤
│ Analyzing requirements...            │  ← New output
│                                      │
│                                      │
└──────────────────────────────────────┘
```

### Window Full (Scrolling)

```
┌──────────────────────────────────────┐
│ 💭 architect thinking...             │
├──────────────────────────────────────┤
│ Task 2: Create database              │  ← Oldest visible
│ Task 3: Implement auth               │
│ Task 4: Add tests                    │
│ Task 5: Deploy                       │
│ Reviewing architecture               │
│ Checking security                    │
│ Validating design                    │
│ Creating handoff                     │
│ Finalizing plan                      │
│ Done                                 │  ← Newest
└──────────────────────────────────────┘
```

Older lines scroll off the top as new ones arrive.

## Technical Details

### ANSI Escape Codes

The window uses ANSI codes for cursor positioning:
- `\033[<N>A` - Move cursor up N lines
- `\r\033[K` - Clear current line
- Box drawing characters: `┌─┐├┤└┘│`

### Terminal Detection

```python
if sys.stdout.isatty():
    # Use live scrolling window
else:
    # Use simple line output
```

### Buffer Management

```python
self.output_buffer = []          # Store lines
self.max_output_lines = 10       # Max to show

# Keep last N lines
if len(buffer) > max_lines:
    buffer = buffer[-max_lines:]
```

### Line Truncation

```python
max_width = terminal_width - 4   # Account for borders
if len(line) > max_width:
    line = line[:max_width - 3] + "..."
```

## Comparison

### Without Output Window

```
[⠹] architect working...
[⠸] architect working...
[⠼] architect working...
...wait...
...wait...
[OK] Done
```

**No visibility** into what's happening!

### With Output Window

```
┌──────────────────────────────────────┐
│ 💭 architect thinking...             │
├──────────────────────────────────────┤
│ Analyzing requirements...            │
│ Breaking down tasks...               │
│ Creating architecture...             │
└──────────────────────────────────────┘
```

**Full transparency** into agent activity!

## Examples

### Example 1: Quick Task (5 lines)

```bash
$ agent-coordinator --workspace . --output-lines 5

┌──────────────────────────────┐
│ 💭 developer thinking...     │
├──────────────────────────────┤
│ Reading requirements         │
│ Implementing feature         │
│ Adding tests                 │
│ Updating handoff             │
│ Complete                     │
└──────────────────────────────┘
```

Compact, shows key steps.

### Example 2: Complex Task (15 lines)

```bash
$ agent-coordinator --workspace . --output-lines 15

┌───────────────────────────────────────┐
│ 💭 architect thinking...              │
├───────────────────────────────────────┤
│ Analyzing project requirements        │
│ Reviewing existing architecture       │
│ Identifying dependencies              │
│ Planning microservices structure      │
│ Designing API contracts               │
│ Defining data models                  │
│ Planning authentication flow          │
│ Designing error handling              │
│ Planning monitoring strategy          │
│ Creating deployment pipeline          │
│ Documenting architecture decisions    │
│ Preparing task breakdown              │
│ Creating acceptance criteria          │
│ Writing handoff document              │
│ Validation complete                   │
└───────────────────────────────────────┘
```

Detailed view of complex reasoning.

### Example 3: Debug Mode (20 lines)

```bash
$ agent-coordinator --workspace . --output-lines 20
```

Maximum visibility for debugging.

## Non-TTY Mode

When output is piped or redirected:

```bash
$ agent-coordinator --workspace . > log.txt

AGENT: ARCHITECT
Backend: copilot | Task: task-001
Analyzing requirements...
Breaking down tasks...
Task 1: Setup authentication
Task 2: Create database
...
[OK] Status: continue | Next: developer
```

Simple line-by-line output, no window.

## Performance

### Overhead

- **Minimal**: Only updates when agent produces output
- **Efficient**: Terminal writes are buffered
- **Responsive**: Updates every ~100ms max

### Memory

- **Buffer size**: N lines × ~100 chars = ~1-5KB
- **Negligible** impact even for long runs

## Customization

### In Code

```python
from agent_coordinator.infrastructure.tui import TUIDisplay

display = TUIDisplay()
display.max_output_lines = 15  # Change window size
```

### Via Config (Future)

```json
{
  "ui": {
    "output_lines": 15,
    "show_window": true
  }
}
```

## Troubleshooting

### Window Not Showing

**Symptom**: No output window, just spinner

**Causes**:
1. Backend doesn't produce stdout
2. Non-TTY environment
3. Quiet mode enabled

**Solutions**:
- Check backend supports output
- Run in terminal (not piped)
- Remove `--quiet` flag

### Flickering

**Symptom**: Window flickers during updates

**Cause**: Terminal doesn't support ANSI codes properly

**Solution**:
- Use modern terminal (iTerm2, Windows Terminal, etc.)
- Update terminal software
- Use `--quiet` to disable window

### Lines Too Long

**Symptom**: Text truncated with "..."

**Cause**: Terminal width smaller than output

**Solutions**:
- Resize terminal window wider
- Agent output is naturally verbose
- This is expected behavior (prevents wrapping)

### Window Too Small/Large

**Symptom**: Not enough/too much visible

**Solution**:
```bash
# Adjust window size
agent-coordinator --output-lines 15  # More lines
agent-coordinator --output-lines 5   # Fewer lines
```

## Best Practices

### 1. Choose Appropriate Size

- **Simple tasks**: 5-7 lines
- **Normal tasks**: 10-12 lines
- **Complex tasks**: 15-20 lines
- **Debug mode**: 20+ lines

### 2. Terminal Width

- **Minimum**: 80 columns
- **Recommended**: 120+ columns
- **Ideal**: Full screen width

### 3. Use Quiet Mode When Appropriate

```bash
# CI/CD pipelines
agent-coordinator --quiet

# Interactive use
agent-coordinator  # Shows window
```

### 4. Redirect for Logging

```bash
# Save full output
agent-coordinator 2>&1 | tee coordinator.log

# Only errors
agent-coordinator 2> errors.log
```

## Future Enhancements

Potential improvements:

1. **Color coding** - Different colors for different message types
2. **Filtering** - Only show warnings/errors
3. **Multiple agents** - Split screen for parallel agents
4. **Replay** - Scroll back through history
5. **Export** - Save window contents to file

## Summary

The output window provides:

✅ **Transparency**: See what agents are doing
✅ **Real-time**: Updates as output arrives  
✅ **Configurable**: Adjust window size
✅ **Adaptive**: Works in TTY and non-TTY modes
✅ **Clean**: Professional box-drawing interface

The window makes agent workflows **observable and debuggable** without overwhelming the user!
