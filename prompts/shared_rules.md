# Shared Session Rules

All agents must follow these rules at all times.

1. **Read before writing** — always read the latest valid handoff block before taking any action.

2. **Respect role boundaries** — do not perform another role's work unless the human operator explicitly changes the rules.

3. **Append-only handoff** — never rewrite or delete prior handoff history during normal operation.

4. **Be explicit** — state status, next actor, blockers, and task ID directly. No implicit assumptions.

5. **No silent assumptions** — if a dependency, requirement, or acceptance criterion is unclear, escalate instead of inventing an answer.

6. **One active task** — do not split into multiple concurrent tasks. One task must complete before the next begins.

7. **Preserve traceability** — use the same task ID consistently across the full review loop.

8. **Stop on human escalation** — if the latest valid block targets `human`, do not continue autonomously.

9. **Completion is explicit** — the workflow is not complete until the architect writes `STATUS: plan_complete`.

10. **Structured block is authoritative** — if natural-language text and the structured block differ, the structured block governs.
