# workspace/

This directory is an example project workspace for the coordinator.

A **workspace** is any directory that contains:

| File | Purpose |
|---|---|
| `handoff.md` | Append-only agent communication log (required) |
| `tasks.json` | Task list with statuses (optional) |
| `plan.md` | Human-readable project plan (optional) |

## Using a different workspace

Point the coordinator at any directory with a valid `handoff.md`:

```bash
python3 coordinator.py --workspace /path/to/your/project
```

## Starting fresh

Copy this directory to your project or create `handoff.md` manually
with an initial `---HANDOFF---` block (see `docs/protocol.md`).
