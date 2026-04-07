# Human Agent Integration

The coordinator supports "human" as a special agent that prompts for human input when needed in the workflow.

## Using the Human Agent

### In Handoff

When an agent sets `NEXT: human`, the coordinator pauses and prompts the human operator:

```markdown
---HANDOFF---
ROLE: architect
STATUS: needs_human
NEXT: human
TASK_ID: task-001
SUMMARY: Need human decision on architectural approach
---END---
```

### Human Prompt

When `NEXT: human`, the coordinator shows:

```
═══════════════════════════════════════════════════════════════════
HUMAN INPUT REQUIRED
────────────────────────────────────────────────────────────────────
Task: task-001
Status: needs_human
────────────────────────────────────────────────────────────────────

The workflow needs your input to continue.

Options:
  r - Respond with guidance (creates new handoff)
  e - Edit handoff.md manually in your editor
  v - View current handoff.md
  q - Quit

────────────────────────────────────────────────────────────────────
Choice [r/e/v/q]:
```

## Human Input Workflow

### Option: Respond (r) - RECOMMENDED

The easiest way to provide input:

1. Choose 'r' for Respond
2. Enter your guidance/response (multi-line, empty line to finish)
3. Specify target agent (default: architect)
4. Coordinator creates new handoff block automatically
5. Workflow continues to the specified agent

**Example:**
```
Choice [r/e/v/q]: r

Provide your response/guidance:
(This will be added to the handoff for the next agent)

> Please implement JWT-based authentication.
> Use bcrypt for password hashing.
> Add rate limiting to login endpoint.
> 

Route to agent [architect/developer/qa_engineer/other]: developer

✓ Response added to handoff.md
✓ Routing to: developer
```

Creates this handoff block:
```markdown
---HANDOFF---
ROLE: human
STATUS: continue
NEXT: developer
TASK_ID: task-001
TITLE: Human response provided
SUMMARY: Human provided guidance and direction for the workflow to continue.

Human response (2026-04-07 09:09:30 UTC):
Please implement JWT-based authentication.
Use bcrypt for password hashing.
Add rate limiting to login endpoint.

ACCEPTANCE:
- Agent acknowledges human guidance
- Agent proceeds with implementation
---END---
```

### Option: Edit (e)

Opens handoff.md directly in your editor for manual editing:

1. Review current state
2. Update status, next agent, summary manually
3. Add guidance or decisions
4. Save and close
5. Coordinator continues

### Option: View (v)

Shows last 50 lines of handoff.md for context.

### Option: Quit (q)

Exit the coordinator.

## When to Use Human Agent

### Architectural Decisions

```markdown
NEXT: human
SUMMARY: Choose between monolithic or microservices architecture
```

### Approval Gates

```markdown
STATUS: needs_human
NEXT: human  
SUMMARY: Review and approve the implementation plan before development
```

### Blocked Situations

```markdown
STATUS: blocked
NEXT: human
SUMMARY: Dependency not available, need human to resolve
```

### Clarifications

```markdown
STATUS: needs_human
NEXT: human
SUMMARY: Ambiguous requirement - need human clarification on error handling
```

## Example Workflow

### Scenario: Approval Gate

```bash
$ agent-coordinator --workspace ./project

[Turn 1]
AGENT: ARCHITECT
[⠹] architect working
[OK] Status: needs_human | Next: human

[Turn 2]

═══════════════════════════════════════════════════════════════════
HUMAN INPUT REQUIRED
────────────────────────────────────────────────────────────────────
Task: task-001
Status: needs_human
────────────────────────────────────────────────────────────────────

Choice [r/e/v/q]: r

Provide your response/guidance:
> Approved. Proceed with implementation.
> Use the proposed microservices architecture.
> 

Route to agent: developer

✓ Response added to handoff.md
✓ Routing to: developer
═══════════════════════════════════════════════════════════════════

[Turn 3]
AGENT: DEVELOPER
[⠹] developer working
...
```

### Scenario: Provide Detailed Guidance

```bash
[Turn 4]

═══════════════════════════════════════════════════════════════════
HUMAN INPUT REQUIRED
────────────────────────────────────────────────────────────────────

Choice [r/e/v/q]: r

Provide your response/guidance:
> Use JWT for authentication:
> - Access token expires in 15 minutes
> - Refresh token expires in 7 days
> - Store tokens in httpOnly cookies
> - Use RS256 algorithm for signing
> - Add rate limiting: 5 requests per minute
> 

Route to agent: developer

✓ Response added to handoff.md
✓ Routing to: developer

# Coordinator continues with your guidance
```

## Routing to Specific Agents

When responding, you can route to any agent:

**Built-in agents:**
- `architect` - For design and planning work
- `developer` - For implementation
- `qa_engineer` - For testing

**Custom agents:**
- Any agent defined in your `agents.json`
- Just type the agent name

**Example:**
```
Route to agent: frontend_dev
Route to agent: backend_engineer  
Route to agent: architect
```

Default is `architect` if you just press Enter.

## Auto-Created Handoff

If handoff.md doesn't exist when you run the coordinator:

```bash
$ agent-coordinator --workspace ./new-project

Handoff file not found: ./new-project/handoff.md
Creating initial handoff.md...

Created initial handoff.md in ./new-project
```

The initial handoff will have:
- `ROLE: architect`
- `STATUS: continue`
- `NEXT: architect`
- Basic template structure

You can then edit it before continuing, or let the architect start.

## Response Format

When you choose 'r' (Respond), the coordinator creates a handoff block with:

- **ROLE: human** - Indicates human provided this input
- **STATUS: continue** - Workflow should continue
- **NEXT: <target>** - Agent you specified
- **TASK_ID** - Same as current task
- **SUMMARY** - Standard template
- **Human response** - Your actual input with timestamp
- **ACCEPTANCE** - Auto-generated criteria
- **CONSTRAINTS** - References your guidance

Agents can then read your guidance from the handoff and proceed.

## Best Practices

### 1. Use 'r' for Quick Responses

The Respond option is fastest for most cases:
- No editor needed
- Automatic handoff creation
- Easy agent targeting

### 2. Use 'e' for Complex Edits

Use manual editing when you need to:
- Modify multiple fields
- Update task status
- Add complex acceptance criteria
- Reference specific files

### 3. Be Specific in Responses

Good response:
```
> Implement authentication using JWT.
> Use the Auth0 library.
> Add unit tests for login/logout.
```

Vague response:
```
> Looks good, proceed.
```

### 4. Target the Right Agent

- **architect** - Needs design, planning, or decomposition
- **developer** - Ready for implementation
- **qa_engineer** - Ready for testing
- **custom** - Your specific agent

## Integration with Agents

Agents can request human input by setting `NEXT: human`:

Example agent prompt template:
```markdown
If you need human input or approval:
- Set NEXT to "human"
- Set STATUS to "needs_human" or "blocked"
- Provide clear SUMMARY of what you need
```

Agents can read human responses from handoff blocks with `ROLE: human`.

## Configuration

No special configuration needed. The "human" agent is built-in and always available.

## Comparison

### Before

Agent needs human input → workflow stops → error message → kill process → manual edit → restart

### After

Agent sets `NEXT: human` → coordinator prompts → human responds → handoff created → workflow continues seamlessly

## Tips

### Quick Approval

```bash
Choice [r/e/v/q]: r
> Approved
> 
Route to agent: developer
```

### Detailed Guidance

```bash
Choice [r/e/v/q]: r
> Implement feature X with these requirements:
> 1. Use library Y version 2.0
> 2. Add comprehensive error handling
> 3. Include integration tests
> 4. Document the API endpoints
> 
Route to agent: developer
```

### Route to Architect for Replanning

```bash
Choice [r/e/v/q]: r
> This approach won't work. Please redesign using pattern X.
> 
Route to agent: architect
```

The human agent makes the coordinator truly interactive and human-in-the-loop ready!

## Human Input Workflow

### Option: Edit (e)

Opens handoff.md directly in your editor:

1. Review current state
2. Update status, next agent, summary
3. Add guidance or decisions
4. Save and close
5. Coordinator continues

### Option: Message (m)

Opens editor for a message/guidance:

1. Write your message in editor
2. Save and close
3. Message appended to handoff as comment
4. Coordinator continues

### Option: View (v)

Shows last 50 lines of handoff.md for context.

### Option: Continue (c)

If you've already updated handoff.md externally, choose this to continue.

### Option: Quit (q)

Exit the coordinator.

## When to Use Human Agent

### Architectural Decisions

```markdown
NEXT: human
SUMMARY: Choose between monolithic or microservices architecture
```

### Approval Gates

```markdown
STATUS: needs_human
NEXT: human  
SUMMARY: Review and approve the implementation plan before development
```

### Blocked Situations

```markdown
STATUS: blocked
NEXT: human
SUMMARY: Dependency not available, need human to resolve
```

### Clarifications

```markdown
STATUS: needs_human
NEXT: human
SUMMARY: Ambiguous requirement - need human clarification on error handling
```

## Example Workflow

### Scenario: Approval Gate

```bash
$ agent-coordinator --workspace ./project

[Turn 1]
AGENT: ARCHITECT
[⠹] architect working
[OK] Status: needs_human | Next: human

[Turn 2]

═══════════════════════════════════════════════════════════════════
HUMAN INPUT REQUIRED
────────────────────────────────────────────────────────────────────
Task: task-001
Status: needs_human
────────────────────────────────────────────────────────────────────

The workflow needs your input to continue.

Choice [e/m/v/c/q]: e

Opening handoff.md in vim...

# Edit the handoff:
# - Review architect's plan
# - Change STATUS to approved
# - Change NEXT to developer
# - Save and quit

Handoff updated
═══════════════════════════════════════════════════════════════════

[Turn 3]
AGENT: DEVELOPER
[⠹] developer working
...
```

### Scenario: Add Guidance

```bash
[Turn 4]

═══════════════════════════════════════════════════════════════════
HUMAN INPUT REQUIRED
────────────────────────────────────────────────────────────────────

Choice [e/m/v/c/q]: m

Opening editor for your message...

# Write guidance:
Make sure to follow the existing code style.
Use ES6 modules for all imports.
Add comprehensive error handling.

# Save and close

Message added to handoff.md
═══════════════════════════════════════════════════════════════════

# Coordinator continues with your guidance
```

## Auto-Created Handoff

If handoff.md doesn't exist when you run the coordinator:

```bash
$ agent-coordinator --workspace ./new-project

Handoff file not found: ./new-project/handoff.md
Creating initial handoff.md...

Created initial handoff.md in ./new-project
```

The initial handoff will have:
- `ROLE: architect`
- `STATUS: continue`
- `NEXT: architect`
- Basic template structure

You can then edit it before continuing, or let the architect start.

## Manual Runner vs Human Agent

### Manual Runner

Set in agents.json:
```json
{
    "agents": {
        "reviewer": {
            "backend": "manual"
        }
    }
}
```

When `NEXT: reviewer`, the coordinator shows the prompt and waits for you to manually update handoff.md.

### Human Agent

No configuration needed - just use `NEXT: human` in handoff:

```markdown
NEXT: human
```

The coordinator detects this and prompts for input.

## Best Practices

### 1. Use for Decisions

```markdown
SUMMARY: Choose database: PostgreSQL or MongoDB?
NEXT: human
```

### 2. Use for Approvals

```markdown
STATUS: review_required
NEXT: human
SUMMARY: Review proposed changes before implementation
```

### 3. Use for Blocked States

```markdown
STATUS: blocked
NEXT: human
SUMMARY: External dependency not ready, need human to unblock
```

### 4. Provide Context

Always include clear SUMMARY explaining what input is needed:

```markdown
SUMMARY: Review the 5 proposed tasks and approve or modify before development begins
NEXT: human
```

## Integration with Agents

Agents can request human input by setting `NEXT: human`:

Example agent prompt template:
```markdown
If you need human input or approval:
- Set NEXT to "human"
- Set STATUS to "needs_human" or "blocked"
- Provide clear SUMMARY of what you need
```

## Configuration

No special configuration needed. The "human" agent is built-in and always available.

### Optional: Add to agents.json for documentation

```json
{
    "agents": {
        "architect": {...},
        "developer": {...},
        "human": {
            "description": "Human operator for decisions and approvals"
        }
    }
}
```

(The coordinator will detect `NEXT: human` even without this.)

## Comparison

### Before

Agent needs human input → workflow stops → error message → kill process → manual edit → restart

### After

Agent sets `NEXT: human` → coordinator prompts → human edits in editor → workflow continues seamlessly

## Tips

### Quick Edit

```bash
# Keep editor ready
export EDITOR="code --wait"

# When human input needed, editor opens immediately
```

### View Context

Always use 'v' to view handoff before editing to understand the current state.

### Update Multiple Fields

When editing, update all relevant fields:
- STATUS (continue, approved, etc.)
- NEXT (which agent should go next)
- SUMMARY (what was done/decided)
- Any other sections

The human agent makes the coordinator truly interactive and human-in-the-loop ready!
