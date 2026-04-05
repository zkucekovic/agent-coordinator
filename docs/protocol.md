# Handoff Protocol

This document describes the complete format and rules for the `handoff.md` communication channel used by the multi-agent coordination workflow.

## File Rules

- `handoff.md` is **append-only** — entries are never edited or deleted during normal operation.
- Each turn by any agent appends one human-readable section followed by one structured `---HANDOFF---` block.
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
ROLE: <agent-role-name>
STATUS: <status-value>
NEXT: <agent-role-name|human|none>
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
| `ROLE` | scalar | Who wrote this block (e.g. `architect`, `developer`, `qa_engineer`) |
| `STATUS` | scalar | Current state of the work (see allowed values below) |
| `NEXT` | scalar | Who acts next: any agent role name, `human`, or `none` |
| `TASK_ID` | scalar | The task identifier (e.g. `task-003`) |
| `TITLE` | scalar | Short human-readable title |
| `SUMMARY` | scalar | What was done or decided this turn |
| `ACCEPTANCE` | list | Acceptance criteria (with PASS/FAIL for implementers, plain for architect) |
| `CONSTRAINTS` | list | Constraints that applied this turn |
| `FILES_TO_TOUCH` | list | Files the implementer is expected to modify |
| `CHANGED_FILES` | list | Files actually modified this turn |
| `VALIDATION` | list | Validation steps run and their results |
| `BLOCKERS` | list | Any blockers, or `none` |

List fields accept `n/a` or `none` as a no-item marker. Both are stripped from the parsed result.

## Allowed STATUS Values

### Architect turn STATUS values

| Value | Meaning |
|---|---|
| `continue` | Assigning a task or providing direction |
| `approved` | Agent output approved; task complete |
| `rework_required` | Agent output rejected; targeted rework requested |
| `blocked` | Architect cannot proceed without information |
| `needs_human` | Escalation to the human operator required |
| `plan_complete` | All tasks done and reviewed; workflow finished |

### Developer turn STATUS values

| Value | Meaning |
|---|---|
| `review_required` | Implementation done; architect review requested |
| `blocked` | Developer cannot proceed; escalating |
| `needs_human` | Human intervention required |

### QA Engineer turn STATUS values

| Value | Meaning |
|---|---|
| `review_required` | Validation complete, all criteria pass; architect review requested |
| `rework_required` | Validation found failures; recommending rework to architect |
| `blocked` | Cannot run validation (environment broken) |
| `needs_human` | Human intervention required |

### Custom agent STATUS values

Custom agents should use `review_required` when their work is done, `blocked` when stuck, and `needs_human` for escalation. The architect determines the next step.

## NEXT Allowed Values

| Value | Meaning |
|---|---|
| `architect` | Architect should act next |
| `developer` | Developer should act next |
| `qa_engineer` | QA engineer should act next |
| `<custom>` | Any custom agent defined in agents.json |
| `human` | Human operator should act next |
| `none` | No further automated action (used with `plan_complete`) |

## Turn Rules

### Architect turn rules

- Must read the latest valid block before writing.
- Must assign tasks one at a time (no concurrent `in_engineering` tasks).
- Must include explicit, testable acceptance criteria for every task assignment.
- Must not write `STATUS: plan_complete` while any task remains unfinished.
- May write `STATUS: rework_required` to send a task back; must specify what to fix.
- Has final authority over all decisions — can challenge or override any agent's output.

### Developer turn rules

- Must confirm `NEXT: developer` in the latest block before acting.
- Must implement only the task identified by `TASK_ID` in the latest architect block.
- Must populate `CHANGED_FILES` and `VALIDATION` — omitting these is a protocol violation.
- Must set `STATUS: blocked` and `NEXT: human` if unable to proceed without guessing.
- Must always set `NEXT: architect` — the architect decides whether to send to QA or proceed.

### QA Engineer turn rules

- Must confirm `NEXT: qa_engineer` in the latest block before acting.
- Must validate against the acceptance criteria stated by the architect.
- Must report PASS/FAIL with evidence for each criterion.
- Must always set `NEXT: architect` — the architect makes the final call.
- Verdict is a recommendation; the architect may accept, challenge, or override.

## Standard Workflow

```
architect --> developer --> architect --> qa_engineer --> architect
                                                            |
                                          approve / challenge / rework
```

The architect routes work between agents. The typical flow is: architect assigns to developer, developer returns to architect, architect sends to QA, QA returns to architect, architect approves or requests rework.

## Completion Rule

The workflow reaches completion when the architect appends a block with:
```
STATUS: plan_complete
NEXT: human
```
No further automated agent turns should occur after this point.

## Blocked Rule

Any agent may escalate by writing:
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
