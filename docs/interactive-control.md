# Interactive Control and TUI Interface

The agent coordinator features a clean terminal UI with full interrupt handling, allowing humans to intervene at any time.

## TUI Interface

### Clean Display

```
════════════════════════════════════════════════════════════════════
AGENT: ARCHITECT
Backend: copilot | Task: task-001 | Status: continue
────────────────────────────────────────────────────────────────────

[⠹] architect working
```

Once the agent completes:

```
────────────────────────────────────────────────────────────────────
[OK] Status: review_required | Next: developer
════════════════════════════════════════════════════════════════════
```

### Animated Thinking Indicator

While the agent is working, you see an animated spinner:
- `[⠋] architect working`
- `[⠙] architect working`
- `[⠹] architect working`
- etc.

The animation provides visual confirmation that the agent is actively working, not frozen.

## Interrupt Handling (Ctrl+C)

Press **Ctrl+C** at any time to interrupt execution and open an interactive menu.

### Interrupt Menu

```
════════════════════════════════════════════════════════════════════
INTERRUPTED (Ctrl+C pressed)
────────────────────────────────────────────────────────────────────

  c - Continue execution
  r - Retry current turn
  e - Edit handoff.md in editor
  m - Add message to handoff
  i - Inspect handoff.md
  q - Quit

────────────────────────────────────────────────────────────────────
Choice [c/r/e/m/i/q]:
```

### Menu Options

#### Continue (c)
Resumes execution from where it was interrupted.

#### Retry (r)
Reruns the current agent turn. Useful if:
- The agent made a mistake
- You want to try again with different context
- The agent got stuck

#### Edit Handoff (e)
Open handoff.md directly in your text editor ($EDITOR or $VISUAL).
- Make direct changes to the handoff
- Fix agent mistakes
- Add or modify sections
- Saves automatically

#### Add Message (m)
Add a human message to handoff.md:
- Opens your text editor with a template
- Write multi-line guidance
- Appended as HTML comment
- Fallback to prompt if editor unavailable

#### Inspect (i)
View the current handoff.md content to understand the state.

#### Quit (q)
Exit the coordinator gracefully.

## Usage Examples

### Basic Workflow with Interrupts

```bash
# Start the coordinator
agent-coordinator --workspace ./my-project

# Let it run...
# Press Ctrl+C when you want to intervene

# Choose an option:
# - 'i' to inspect current state
# - 'm' to add guidance
# - 'c' to continue
# - 'q' to exit
```

### Common Scenarios

#### Check Progress Mid-Execution

```bash
$ agent-coordinator --workspace ./my-project
[Turn 1]
AGENT: ARCHITECT
[⠹] architect working

^C  # Press Ctrl+C

Choice [c/r/u/m/i/q]: i

Current handoff.md:
────────────────────────────────────────────────────
[shows handoff content]
────────────────────────────────────────────────────

Press Enter to continue...

Choice [c/r/u/m/i/q]: c
# Continues...
```

#### Add Human Guidance

```bash
$ agent-coordinator --workspace ./my-project
[Turn 3]
AGENT: DEVELOPER
[⠹] developer working

^C  # Press Ctrl+C

Choice [c/r/u/m/i/q]: m

Enter message (empty line to finish):
> Make sure to use ES6 modules
> Follow the coding style in existing files
> 

SUCCESS: Message added to handoff.md
Choice [c/r/u/m/i/q]: c
# Continues with your message added
```

#### Retry a Turn

```bash
$ agent-coordinator --workspace ./my-project
[Turn 2]
AGENT: DEVELOPER
[⠹] developer working
[output shows the agent made a mistake]

^C  # Press Ctrl+C

Choice [c/r/u/m/i/q]: r
# Retries the current turn
```

## Technical Details

### Signal Handling

The coordinator uses Python's `signal` module to catch SIGINT (Ctrl+C):
- Gracefully stops the thinking animation
- Shows interactive menu
- Waits for user choice
- Resumes or exits based on selection

### Thread Safety

- Thinking indicator runs in a daemon thread
- Proper cleanup on interrupt
- No hanging threads
- Clean shutdown

### Menu Implementation

- Simple text-based interface
- Single-key choices
- Re-prompts on invalid input
- Handles EOF and nested interrupts

## Benefits

### For Development

- **Inspect state** at any point
- **Add guidance** when agents go off track
- **Retry turns** that fail
- **Quick exit** when needed

### For Debugging

- **See exactly where** something went wrong
- **Add context** mid-execution
- **Control flow** without killing process
- **Clean state** management

### For Collaboration

- **Human-in-the-loop** capability
- **Document interventions** in handoff
- **Review before continuing**
- **Graceful coordination**

## Implementation Notes

### No Emoticons

The interface uses clean ASCII/Unicode characters:
- `[⠹]` for animation (Braille characters)
- `[OK]` and `[FAILED]` for status
- `─` and `═` for boxes
- Plain text labels

### TTY Detection

- Automatically adapts to environment
- Animation in TTY, static text otherwise
- Works in pipes, redirects, and CI/CD
- No configuration needed

### Future Enhancements

Potential additions:
- Implement undo functionality
- Add edit handoff option
- Show recent history
- Task list view
- Configuration reload

## Comparison to Other Tools

Similar to Claude Code's interrupt handling:
- Ctrl+C opens interactive menu
- Options to continue, retry, or intervene
- Clean resumption after intervention
- User maintains control

But with added benefits:
- Multi-agent coordination
- Task-aware interventions
- Event logging of all actions
- Backend-agnostic design
