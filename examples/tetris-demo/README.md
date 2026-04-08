# Demo: Tetris Game

This example demonstrates the full agent coordinator workflow by building a playable Tetris game from a project brief.

## What it does

Three agents collaborate to produce a single-file HTML Tetris game:

1. The **architect** reads `plan.md`, breaks the work into tasks, and assigns them one at a time
2. The **developer** implements each task and reports back
3. The **QA engineer** validates the work against acceptance criteria
4. The **architect** reviews QA's verdict, approves or requests rework, and assigns the next task
5. The loop continues until the architect declares the project complete

The result is a fully playable `tetris.html` file that runs in any browser.

## Running the demo

From the repository root:

```bash
# Using OpenCode (default)
agent-coordinator --workspace examples/tetris-demo

# Using Claude Code
agent-coordinator --workspace examples/tetris-demo
# (set default_backend to "claude" in agents.json first)

# Watch with verbose output
agent-coordinator --workspace examples/tetris-demo --max-turns 30
```

The coordinator will run the full architect-developer-QA loop. When it finishes, open `examples/tetris-demo/tetris.html` in your browser.

## What's in this directory

| File | Purpose |
|---|---|
| `SPECIFICATION.md` | Project specification — the requirements the architect works from |
| `handoff.md` | Initial handoff block that starts the workflow |
| `tasks.json` | Empty task registry (the architect will populate it) |

After the coordinator runs, you'll also see:

| File | Created by |
|---|---|
| `plan.md` | The architect (implementation plan) |
| `tetris.html` | The developer agent |
| `.agent-coordinator/events.jsonl` | Audit log of every agent turn |
| `.agent-coordinator/sessions.json` | Saved session IDs for continuity |

## Expected workflow

The architect will likely decompose the work into tasks like:

1. Core game board and rendering (canvas, grid, draw loop)
2. Tetromino definitions and spawning (all 7 pieces with colors)
3. Movement and rotation with collision detection and wall kicks
4. Line clearing, scoring, and level progression
5. UI elements (score display, next piece preview, game over screen)
6. Controls (keyboard input, pause functionality)

Each task goes through the full cycle: architect assigns, developer implements, QA validates, architect approves. Expect 15-25 turns depending on how many rework cycles occur.

## Notes

- The demo uses whichever backend is configured in `agents.json` at the repository root
- To start over, delete `handoff.md` and restore it from git, or use `--reset` to clear sessions
- The generated Tetris game is a real, playable game — not a stub or placeholder
