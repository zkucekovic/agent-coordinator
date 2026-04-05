# Handoff Protocol

This document describes the complete format and rules for the `handoff.md` communication channel used by the two-agent coordination workflow.

## File Rules

- `handoff.md` is **append-only** — entries are never edited or deleted during normal operation.
- Each turn by architect or engineer appends one human-readable section followed by one structured `---HANDOFF---` block.
- The structured block is authoritative; if narrative text and the block contradict, the block governs.

## Entry Format

Each handoff entry consists of:

1. A Markdown heading with ISO timestamp and role:
   ```
   ## 2026-04-05T12:00:00Z — Architect
   ```
2. Optional free-text explanation, notes, or task description.
3. A structured block in the exact format shown below.

### Structured Block Format

```
---HANDOFF---
ROLE: <architect|engineer>
STATUS: <status-value>
NEXT: <architect|engineer|human|none>
TASK_ID: <task-id>
TITLE: <short title>
SUMMARY: <single-line or multi-line explanation>
ACCEPTANCE:
- <acceptance criterion>
- <acceptance criterion>
CONSTRAINTS:
- <constraint>
FILES_TO_TOUCH:
- <filename>
CHANGED_FILES:
- <filename>
VALIDATION:
- <validation step and result>
BLOCKERS:
- <blocker description or "none">
---END---
```

## Required Fields

| Field | Type | Description |
|---|---|---|
| `ROLE` | scalar | Who wrote this block: `architect` or `engineer` |
| `STATUS` | scalar | Current state of the work (see allowed values below) |
| `NEXT` | scalar | Who acts next: `architect`, `engineer`, `human`, or `none` |
| `TASK_ID` | scalar | The task identifier (e.g. `task-003`) |
| `TITLE` | scalar | Short human-readable title |
| `SUMMARY` | scalar | What was done or decided this turn |
| `ACCEPTANCE` | list | Acceptance criteria (with PASS/FAIL for engineer, plain for architect) |
| `CONSTRAINTS` | list | Constraints that applied this turn |
| `FILES_TO_TOUCH` | list | Files the engineer is expected to modify |
| `CHANGED_FILES` | list | Files actually modified this turn |
| `VALIDATION` | list | Validation steps run and their results |
| `BLOCKERS` | list | Any blockers, or `none` |

List fields accept `n/a` or `none` as a no-item marker. Both are stripped from the parsed result.

## Allowed STATUS Values

### Architect turn STATUS values

| Value | Meaning |
|---|---|
| `continue` | Assigning a task or providing direction |
| `approved` | Engineer output approved; task complete |
| `rework_required` | Engineer output rejected; targeted rework requested |
| `blocked` | Architect cannot proceed without information |
| `needs_human` | Escalation to the human operator required |
| `plan_complete` | All tasks done and reviewed; workflow finished |

### Engineer turn STATUS values

| Value | Meaning |
|---|---|
| `review_required` | Implementation done; architect review requested |
| `blocked` | Engineer cannot proceed; escalating |
| `needs_human` | Human intervention required |

## NEXT Allowed Values

| Value | Meaning |
|---|---|
| `architect` | Architect should act next |
| `engineer` | Engineer should act next |
| `human` | Human operator should act next |
| `none` | No further automated action (used with `plan_complete`) |

## Turn Rules

### Architect turn rules

- Must read the latest valid block before writing.
- Must assign tasks one at a time (no concurrent `in_engineering` tasks).
- Must include explicit, testable acceptance criteria for every engineering assignment.
- Must not write `STATUS: plan_complete` while any task remains unfinished.
- May write `STATUS: rework_required` to send a task back; must specify what to fix.

### Engineer turn rules

- Must confirm `NEXT: engineer` in the latest block before acting.
- Must implement only the task identified by `TASK_ID` in the latest architect block.
- Must populate `CHANGED_FILES` and `VALIDATION` — omitting these is a protocol violation.
- Must set `STATUS: blocked` and `NEXT: human` if unable to proceed without guessing.

## Completion Rule

The workflow reaches completion when the architect appends a block with:
```
STATUS: plan_complete
NEXT: human
```
No further automated agent turns should occur after this point.

## Blocked Rule

Either agent may escalate by writing:
```
STATUS: blocked
NEXT: human
```
or:
```
STATUS: needs_human
NEXT: human
```
The human operator reads the block, resolves the issue, and resumes by injecting a new instruction into `handoff.md`.
