# Custom Backend Configuration

The agent coordinator supports any CLI tool as a backend. Built-in support exists for `opencode`, `claude`, and `manual`, but you can configure any other tool using the generic runner.

## Quick Start

To use a custom backend, add a `backend_config` section to your agent configuration in `agents.json`:

```json
{
    "agents": {
        "architect": {
            "backend": "my-tool",
            "backend_config": {
                "command": ["my-tool", "run"],
                "message_arg": "{message}",
                "workspace_arg": ["--dir", "{workspace}"],
                "output_format": "text"
            },
            "prompt_file": "prompts/architect.md"
        }
    }
}
```

## Configuration Reference

### Required Fields

- **`command`** (list of strings): The base command to execute
  ```json
  "command": ["my-tool", "run"]
  ```

### Optional Fields

- **`message_arg`** (string): Template for the message/prompt argument. Defaults to `"{message}"`
  ```json
  "message_arg": "{message}"
  "message_arg": "--prompt={message}"
  ```

- **`workspace_arg`** (list of strings): Template for workspace/directory argument
  ```json
  "workspace_arg": ["--dir", "{workspace}"]
  "workspace_arg": ["--cwd={workspace}"]
  ```

- **`session_arg`** (list of strings): Template for session/context continuation
  ```json
  "session_arg": ["--session", "{session_id}"]
  "session_arg": ["--continue", "--session-id", "{session_id}"]
  ```

- **`model_arg`** (list of strings): Template for model selection
  ```json
  "model_arg": ["--model", "{model}"]
  ```

- **`output_format`** (string): How to parse the command's output. Options:
  - `"text"` (default): Treats stdout as plain text
  - `"json"`: Expects a single JSON object
  - `"jsonl"`: Expects JSON lines (one JSON object per line)

- **`json_text_field`** (string): For JSON output, which field contains the response text
  - Default: `"result"` for `json` format, `"text"` for `jsonl` format
  ```json
  "json_text_field": "response"
  ```

- **`json_session_field`** (string): For JSON output, which field contains the session ID
  - Default: `"session_id"` for `json` format, `"sessionID"` for `jsonl` format
  ```json
  "json_session_field": "session_id"
  ```

## Examples

### Example 1: Simple Text Output Tool

```json
{
    "agents": {
        "developer": {
            "backend": "simple-ai",
            "backend_config": {
                "command": ["simple-ai", "chat"],
                "message_arg": "{message}",
                "workspace_arg": ["--working-dir", "{workspace}"],
                "output_format": "text"
            },
            "prompt_file": "prompts/developer.md"
        }
    }
}
```

Command executed: `simple-ai chat "your prompt here" --working-dir /path/to/workspace`

### Example 2: JSON Output with Session Support

```json
{
    "agents": {
        "architect": {
            "backend": "custom-llm",
            "backend_config": {
                "command": ["custom-llm", "execute"],
                "message_arg": "--prompt={message}",
                "workspace_arg": ["--dir={workspace}"],
                "session_arg": ["--session={session_id}"],
                "model_arg": ["--model={model}"],
                "output_format": "json",
                "json_text_field": "response",
                "json_session_field": "id"
            },
            "model": "gpt-4",
            "prompt_file": "prompts/architect.md"
        }
    }
}
```

Expected JSON output format:
```json
{
    "response": "Agent's text response here",
    "id": "session-abc123"
}
```

### Example 3: JSON Lines (Like OpenCode)

```json
{
    "agents": {
        "qa_engineer": {
            "backend": "streaming-ai",
            "backend_config": {
                "command": ["streaming-ai", "run"],
                "message_arg": "{message}",
                "workspace_arg": ["--dir", "{workspace}"],
                "session_arg": ["--session", "{session_id}"],
                "output_format": "jsonl",
                "json_text_field": "content",
                "json_session_field": "session"
            },
            "prompt_file": "prompts/qa_engineer.md"
        }
    }
}
```

Expected JSONL output format (one JSON object per line):
```jsonl
{"type": "init", "session": "xyz789"}
{"type": "text", "content": "Starting analysis..."}
{"type": "text", "content": "Found issue..."}
{"type": "complete", "session": "xyz789"}
```

### Example 4: OpenCode-Compatible Custom Tool

To replicate OpenCode's behavior with a custom tool:

```json
{
    "backend_config": {
        "command": ["my-opencode-clone", "run"],
        "message_arg": "{message}",
        "workspace_arg": ["--dir", "{workspace}"],
        "session_arg": ["--continue", "--session", "{session_id}"],
        "model_arg": ["--model", "{model}"],
        "output_format": "jsonl",
        "json_text_field": "text",
        "json_session_field": "sessionID"
    }
}
```

The tool should output JSON lines where text events look like:
```json
{"type": "text", "part": {"text": "chunk of response"}, "sessionID": "abc123"}
```

### Example 5: Claude-Compatible Custom Tool

To replicate Claude Code's behavior:

```json
{
    "backend_config": {
        "command": ["my-claude-clone", "--print", "--output-format", "json"],
        "message_arg": "{message}",
        "workspace_arg": ["--cwd", "{workspace}"],
        "session_arg": ["--continue", "--session-id", "{session_id}"],
        "model_arg": ["--model", "{model}"],
        "output_format": "json",
        "json_text_field": "result",
        "json_session_field": "session_id"
    }
}
```

## Mixed Backend Configuration

You can use different backends for different agents in the same workflow:

```json
{
    "default_backend": "opencode",
    "agents": {
        "architect": {
            "backend": "opencode",
            "prompt_file": "prompts/architect.md"
        },
        "developer": {
            "backend": "custom-coder",
            "backend_config": {
                "command": ["custom-coder", "execute"],
                "message_arg": "{message}",
                "workspace_arg": ["--dir", "{workspace}"],
                "output_format": "text"
            },
            "prompt_file": "prompts/developer.md"
        },
        "qa_engineer": {
            "backend": "claude",
            "model": "claude-3-5-sonnet-20241022",
            "prompt_file": "prompts/qa_engineer.md"
        }
    }
}
```

## Troubleshooting

### Command Not Found

If you get a "command not found" error, ensure:
1. The tool is installed and in your PATH
2. The command in `backend_config.command` is correct
3. Try running the command manually first

### Invalid Output Format

If the coordinator can't parse the output:
1. Run your tool manually and check its output format
2. Verify the `output_format` setting matches
3. Check that `json_text_field` and `json_session_field` match your tool's JSON structure
4. Use `--verbose` flag to see the raw output

### Session Not Preserved

If the agent loses context between turns:
1. Verify your tool supports session/context continuation
2. Check that `session_arg` is configured correctly
3. Ensure your tool outputs the session ID in the expected field
4. Check `workflow_events.jsonl` to see if session IDs are being captured

## Testing Your Configuration

Test your backend configuration with a minimal workspace:

```bash
mkdir test-workspace
cd test-workspace
echo '---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: architect
TASK_ID: test-001
TITLE: Test task
SUMMARY: Testing custom backend configuration
ACCEPTANCE:
- Test passes
CONSTRAINTS:
- None
FILES_TO_TOUCH:
- handoff.md
CHANGED_FILES:
- None
VALIDATION:
- None
BLOCKERS:
- None
---END---' > handoff.md

# Create agents.json with your custom backend config
# Then run:
agent-coordinator --workspace . --max-turns 1
```

Check the output for any errors and verify the agent's response.
