# Helper Agent

The **helper agent** is a lightweight utility agent that performs administrative tasks using a cheap, fast model (like Claude Haiku).

## Purpose

The helper agent handles:
- **Formatting** human input into proper handoff blocks
- **Summarizing** workflow history
- **Validating** handoff structure
- **Extracting** key information from unstructured text

## Configuration

In `agents.json`:

```json
{
  "agents": {
    "helper": {
      "model": "claude-3-5-haiku-20241022",
      "backend": "claude",
      "prompt_file": "prompts/helper.md"
    }
  }
}
```

**Key points:**
- Uses **cheap model** (Haiku) for cost efficiency
- Fast execution for quick tasks
- No heavy reasoning required

## When to Use

### 1. Format Human Input

**Before** (human writes informal text):
```
Please add authentication with JWT and use bcrypt for passwords
```

**After** (helper formats to proper handoff):
```markdown
---HANDOFF---
ROLE: human
STATUS: continue
NEXT: developer
TASK_ID: task-001
TITLE: Authentication requirements
SUMMARY: Human provided guidance for authentication implementation.

Requirements:
- Implement JWT-based authentication
- Use bcrypt for password hashing

ACCEPTANCE:
- JWT authentication working
- Passwords hashed with bcrypt
- Tests pass
---END---
```

### 2. Summarize Workflow

Input: 50 handoff blocks
Output: Concise summary of key decisions and state

### 3. Validate Format

Input: Handoff block
Output: Validation report with any syntax/format issues

### 4. Extract Information

Input: Unstructured meeting notes
Output: Structured action items and requirements

## Using from Human Prompt

When you provide human input, you can optionally format it with the helper:

```
Choice [r/e/v/q]: r

Provide your response/guidance:
> Add login page with email/password
> Use OAuth for Google and GitHub  
> Store sessions in Redis
> 

Route to agent: developer

Format with helper agent first? [y/N]: y

✓ Routing to helper agent for formatting
  Helper will format and route to: developer
```

**Flow:**
1. Human provides informal guidance
2. Helper agent formats it properly
3. Helper routes to target agent (developer)
4. Developer receives well-structured handoff

## Workflow Examples

### Example 1: Direct Human → Agent

```
Human input: "Use PostgreSQL for storage"
→ Creates basic handoff
→ Routes to: developer
```

Result: Simple handoff with human's exact words.

### Example 2: Human → Helper → Agent

```
Human input: "Use PostgreSQL for storage"
→ Routes to: helper
→ Helper formats and structures
→ Routes to: developer
```

Result: Professional handoff with:
- Structured requirements
- Extracted constraints
- Proper acceptance criteria
- File references

## Cost Optimization

### Why Use Helper?

**Without helper** (using expensive model for formatting):
- Cost: $0.10 per formatting task
- Time: 5-10 seconds

**With helper** (using Haiku):
- Cost: $0.01 per formatting task
- Time: 1-2 seconds

**Savings**: 10x cheaper, 5x faster for administrative tasks!

### When NOT to Use Helper

Don't use helper for:
- Complex architectural decisions
- Code implementation
- System design
- Multi-turn reasoning

Use helper ONLY for:
- Formatting and structure
- Quick summaries
- Validation checks
- Information extraction

## Integration Patterns

### Pattern 1: Always Format with Helper

Set up a workflow where all human input goes through helper:

```bash
Human → Helper → Architect/Developer/QA
```

Benefits:
- Consistent formatting
- Better structure
- Reduced errors

### Pattern 2: Optional Formatting

Let user choose when to use helper:

```bash
Human → [Format with helper? y/n] → Agent
```

Benefits:
- Flexibility
- Skip helper for simple inputs
- Use helper for complex inputs

### Pattern 3: Automatic Formatting

Detect unstructured input and automatically route to helper:

```python
if is_unstructured(input):
    route_to("helper")
else:
    route_to(target_agent)
```

## Helper Agent Capabilities

### ✅ What Helper Does Well

- **Format** unstructured → structured
- **Validate** handoff syntax
- **Extract** key points from text
- **Summarize** conversations
- **Clean up** messy output
- **Standardize** format

### ❌ What Helper Should NOT Do

- Make architectural decisions
- Write code
- Design systems
- Plan implementations
- Make trade-off decisions
- Multi-turn reasoning

## Example Transformations

### Transformation 1: Informal → Formal

**Input:**
```
hey can we add a login page? needs email and password.
also google oauth would be nice. oh and store sessions in redis.
```

**Helper Output:**
```markdown
---HANDOFF---
ROLE: helper
STATUS: continue
NEXT: developer
TASK_ID: task-001
TITLE: Authentication feature requirements
SUMMARY: Formatted human requirements for login and authentication.

Requirements:
1. Login page with email/password authentication
2. Google OAuth integration
3. Session storage in Redis

ACCEPTANCE:
- Login page functional
- Email/password auth working
- Google OAuth working
- Sessions stored in Redis

CONSTRAINTS:
- Follow OAuth 2.0 standards
- Secure session handling

FILES_TO_TOUCH:
- auth/login.html
- auth/oauth.py
- config/redis.conf
---END---
```

### Transformation 2: Extract from Meeting Notes

**Input:**
```
Meeting notes 2024-04-07:
- Discussed authentication approach
- Team agreed on JWT tokens
- Sarah mentioned using bcrypt for passwords
- Tom wants rate limiting on login
- Deploy by end of week
```

**Helper Output:**
```markdown
---HANDOFF---
ROLE: helper
STATUS: continue
NEXT: developer
TASK_ID: task-002
TITLE: Authentication implementation decisions
SUMMARY: Extracted action items from meeting notes.

Decisions:
- Use JWT tokens for authentication
- Use bcrypt for password hashing
- Implement rate limiting on login endpoint

Timeline:
- Target deployment: End of week

ACCEPTANCE:
- JWT authentication implemented
- Bcrypt password hashing
- Rate limiting active
- Ready for deployment

CONSTRAINTS:
- Must complete by end of week
---END---
```

## Configuration Examples

### Minimal (Recommended)

```json
{
  "agents": {
    "helper": {
      "model": "claude-3-5-haiku-20241022",
      "backend": "claude"
    }
  }
}
```

Uses default prompt from `prompts/helper.md`.

### Custom Model

```json
{
  "agents": {
    "helper": {
      "model": "gpt-3.5-turbo",
      "backend": "openai"
    }
  }
}
```

Use GPT-3.5 instead of Haiku.

### Custom Prompt

```json
{
  "agents": {
    "helper": {
      "model": "claude-3-5-haiku-20241022",
      "backend": "claude",
      "prompt_file": "prompts/custom_helper.md"
    }
  }
}
```

Customize helper behavior.

## Direct Invocation

You can route to helper explicitly:

```
Route to agent: helper
```

Helper will:
1. Read the handoff
2. Perform the requested task
3. Route to next agent

## Best Practices

### 1. Use Cheap Models

Helper doesn't need expensive models:
- ✅ Haiku ($0.25/$1.25 per MTok)
- ✅ GPT-3.5 Turbo
- ❌ Sonnet (too expensive for formatting)
- ❌ GPT-4 (overkill)

### 2. Keep Tasks Simple

Helper should complete in **one turn**:
- ✅ Format this input
- ✅ Extract key points
- ✅ Validate format
- ❌ Design a system (multi-turn)
- ❌ Implement feature (too complex)

### 3. Always Specify Target

Helper should know where to route:

```markdown
Target agent: developer
```

Include in the handoff to helper.

### 4. Validate Helper Output

Helper is cheap but not perfect. Critical tasks should:
1. Use helper for initial formatting
2. Review the output
3. Adjust if needed

## Cost Analysis

### Scenario: 100 Human Inputs/Day

**Without Helper** (all using Sonnet):
```
100 inputs × $0.10 = $10/day
$10 × 30 days = $300/month
```

**With Helper** (formatting with Haiku):
```
100 inputs × $0.01 = $1/day
$1 × 30 days = $30/month
```

**Savings: $270/month (90%)**

### Scenario: Mixed Usage

50 simple inputs → helper ($0.01)
50 complex inputs → direct to architect ($0.10)

```
(50 × $0.01) + (50 × $0.10) = $5.50/day
$5.50 × 30 = $165/month
```

**Savings: $135/month (45%)**

## Troubleshooting

### Helper Not Available

**Symptom**: "Unknown agent: helper"

**Solution**: Add to agents.json:
```json
{
  "agents": {
    "helper": {
      "model": "claude-3-5-haiku-20241022",
      "backend": "claude"
    }
  }
}
```

### Helper Output Incorrect

**Symptom**: Helper formats incorrectly

**Solutions**:
1. Provide clearer input
2. Customize helper prompt
3. Use more capable model
4. Skip helper for this task

### Helper Too Slow

**Symptom**: Helper takes too long

**Solutions**:
1. Check model/backend
2. Ensure using cheap model (Haiku)
3. Simplify the task

## Summary

The helper agent is a **cost-effective utility** for administrative tasks:

✅ **Use it for**: Formatting, validation, extraction, summaries
✅ **Benefits**: 10x cheaper, 5x faster than expensive models
✅ **Model**: Haiku or GPT-3.5 Turbo
✅ **Integration**: Optional in human prompt workflow

The helper agent keeps costs low while maintaining high-quality structured output!
