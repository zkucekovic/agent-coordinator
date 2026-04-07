# Architect → Developer Handoff

## Task: Redesign TUI with Pinned Status Bar

### Problem
Current TUI uses ANSI cursor saves/restores to fake a "status bar at top" — it breaks on scroll, 
races with streaming output, and is not a true separate buffer. The output window redraws 
in-place, causing visual glitches when content scrolls.

### Architecture Decision
Use the **alternate screen buffer** approach — same technique as nano, vim, htop, etc.
- `\033[?1049h` — enter alternate screen (saves terminal state, clears to blank)  
- `\033[?1049l` — exit alternate screen (restores original terminal)
- Inside the alternate screen, we own the full terminal. We can use cursor positioning to:
  - Reserve the LAST line for the pinned status bar
  - Use lines 1 to (rows-1) as the scrolling content area (via a virtual scroll buffer)

This is the ONLY correct way to get a truly pinned, non-scrolling status bar in a terminal.

### Layout (inside alternate screen)
```
┌─────────────────────────────────────────────────────────┐  row 1
│  [Turn N]  AGENT COORDINATOR                            │  header (static)
├─────────────────────────────────────────────────────────┤  row 2  
│                                                         │
│   <scrolling content area>                              │  rows 3 .. (rows-2)
│   agent output, turn headers, handoff transitions       │
│                                                         │
├─────────────────────────────────────────────────────────┤  row (rows-1)
│ ● architect  ○ developer  ○ qa_engineer  | turn 2/30   │  STATUS BAR — PINNED
└─────────────────────────────────────────────────────────┘  row rows
```

### Status Bar Content
- One slot per agent (from agents.json) 
- Dot colors:  ● green (currently running/thinking), ● yellow (last was warning/blocked), ● red (error), ○ gray (idle)
- Dot blinks when agent is active
- Right side: `turn N/MAX | workspace`
- Background: dark gray (`\033[48;5;236m`) — looks like nano/vim status line

### Scrolling Content Area
Since we're in alternate screen, normal `print()` won't scroll properly. 
We maintain a `_lines: list[str]` ring buffer (max = content rows). 
Each time we add output we re-render the content region by:
1. Moving cursor to row 3
2. Clearing and redrawing each content line
3. Moving cursor to bottom of content area (before status bar)
4. Updating status bar in last row

This is efficient: we only re-render when content changes.

### Files to Create/Modify
1. **`agent_coordinator/infrastructure/tui.py`** — REPLACE entirely with new implementation
   - `StatusBar` — owns the bottom row, blinking agent dots, thread-safe updates
   - `ContentArea` — owns rows 3..(rows-2), ring buffer, renders content
   - `Screen` — enters/exits alternate screen, owns layout, public API
   - `InterruptMenu` — keep functionality, adapt to work inside alternate screen (exit alt screen, show menu, re-enter)
   
2. **`agent_coordinator/infrastructure/output_display.py`** — THIN WRAPPER only
   - `create_display()` returns a `Screen` instance when stdout is TTY, `SimpleProgressDisplay` otherwise
   - `SimpleProgressDisplay` unchanged (non-TTY fallback)

3. **`agent_coordinator/cli.py`** — NO changes needed; existing `display.start_agent_turn()`, 
   `display.update_output()`, `display.finish_agent_turn()` API is preserved

### Status Bar Agent States
```python
class AgentState(Enum):
    IDLE    = "idle"     # ○ gray
    RUNNING = "running"  # ● green blinking
    DONE    = "done"     # ● green steady (last turn succeeded)
    ERROR   = "error"    # ● red steady
    BLOCKED = "blocked"  # ● yellow steady
```

### Constraints
- Must degrade gracefully to `SimpleProgressDisplay` when not a TTY (pipes, CI, redirect)
- `--no-streaming` flag must still work (just don't call update_output mid-turn)
- Terminal resize: on SIGWINCH, re-query terminal size and re-render
- On exit (normal or Ctrl+C), ALWAYS call `screen.close()` to restore terminal
- Thread safety: status bar animates in a daemon thread; content writes happen in main thread
  → use a threading.Lock for writes to the terminal

### DO NOT
- Do not use `curses` — it adds heavy dependencies and makes streaming harder
- Do not use `blessed`/`rich`/`textual` — no new dependencies
- Pure ANSI escape codes only

### Acceptance
- Status bar stays pinned at bottom even when agent streams 100+ lines
- Dots blink correctly per agent state  
- Terminal is fully restored after exit (no leftover alt-screen)
- Works at 80-col and wide terminals
- Ctrl+C interrupt menu works and returns to correct state

---
STATUS: ready_for_dev
NEXT: developer

---

## Developer → Architect Report

### Status: COMPLETE ✓

### What was built

**`agent_coordinator/infrastructure/tui.py`** — fully rewritten:

- `Screen` class enters `\033[?1049h` alternate screen on `start_run()`, exits cleanly on `close()`
- Pinned status bar at row `rows` (last row) — never touched by scrolling content
- Dark-gray background (`\033[48;5;236m`) exactly like nano/vim
- Per-agent dots: ○ gray (idle), ● green blinking (running), ● green steady (done), ● red (error), ● yellow (blocked)
- Spinner animation next to active agent (braille frames, 150ms tick)
- Content ring-buffer: adds lines, re-renders only content region + status bar (not full screen)
- `SIGWINCH` handler: re-queries terminal size, full re-render on resize  
- Thread-safe: `threading.Lock` guards all terminal writes
- `InterruptMenu` pauses alt-screen (`\033[?1049l`), shows menu in normal scroll mode, re-enters on return
- `SimpleProgressDisplay` (non-TTY fallback) unchanged in behavior
- `TUIDisplay = Screen` alias for any external code still using the old name

**`agent_coordinator/cli.py`** — minimal changes:
- `run_coordinator()` now uses `create_display()` + `InterruptMenu(display)`
- Calls `display.start_run(agents, workspace, max_turns)` before the loop
- Wraps entire loop in `try/finally: display.close()` — terminal always restored
- `KeyboardInterrupt` handler now delegates to `interrupt_menu.show()`
- All other call sites (`start_agent_turn`, `update_output`, `finish_agent_turn`) unchanged

### Verified
- `python -c "import agent_coordinator.cli"` → OK
- `python -c "import agent_coordinator.infrastructure.tui"` → OK  
- 31 existing tests → all pass
- Visual smoke test → alternate screen entered/exited, status bar animated, terminal restored

STATUS: done
NEXT: architect
