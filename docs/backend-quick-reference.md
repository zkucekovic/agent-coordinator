# Backend Quick Reference

## Built-in Backends

| Backend | Description | Installation |
|---------|-------------|--------------|
| `copilot` | GitHub Copilot CLI | `npm install -g @githubnext/github-copilot-cli` |
| `opencode` | OpenCode AI CLI | `npm install -g opencode` |
| `claude` | Claude Code CLI | See [Claude docs](https://docs.anthropic.com/en/docs/claude-code) |
| `manual` | Human operator | Built-in |

## Using Custom Backends

Any CLI tool can be used as a backend by adding `backend_config` to agents.json:

```json
{
    "agents": {
        "developer": {
            "backend": "your-tool-name",
            "backend_config": {
                "command": ["your-tool", "run"],
                "message_arg": "{message}",
                "output_format": "text"
            }
        }
    }
}
```

## Configuration Templates

### Plain Text Output
```json
"backend_config": {
    "command": ["my-tool", "chat"],
    "message_arg": "{message}",
    "workspace_arg": ["--dir", "{workspace}"],
    "output_format": "text"
}
```

### JSON Output
```json
"backend_config": {
    "command": ["my-tool", "run"],
    "message_arg": "{message}",
    "workspace_arg": ["--dir", "{workspace}"],
    "session_arg": ["--session", "{session_id}"],
    "model_arg": ["--model", "{model}"],
    "output_format": "json",
    "json_text_field": "result",
    "json_session_field": "session_id"
}
```

### JSON Lines (Streaming)
```json
"backend_config": {
    "command": ["my-tool", "stream"],
    "message_arg": "{message}",
    "workspace_arg": ["--dir", "{workspace}"],
    "session_arg": ["--session", "{session_id}"],
    "output_format": "jsonl",
    "json_text_field": "text",
    "json_session_field": "sessionID"
}
```

## Output Format Details

### `"text"` (default)
- Treats stdout as plain text
- No JSON parsing
- Session ID not automatically extracted

### `"json"`
- Expects single JSON object on stdout
- Extracts text from `json_text_field` (default: `"result"`)
- Extracts session from `json_session_field` (default: `"session_id"`)

Example output:
```json
{"result": "Agent response here", "session_id": "abc123"}
```

### `"jsonl"`
- Expects JSON Lines (one JSON object per line)
- Streams text chunks as they arrive
- Looks for text in `json_text_field` or `part.json_text_field`
- Extracts session from `json_session_field` (default: `"sessionID"`)

Example output:
```jsonl
{"sessionID": "xyz789"}
{"type": "text", "part": {"text": "Chunk 1"}}
{"type": "text", "part": {"text": "Chunk 2"}}
```

## Common Patterns

### Session Continuation
If your tool supports session/context continuation:
```json
"session_arg": ["--session", "{session_id}"]
"session_arg": ["--continue", "--session-id", "{session_id}"]
```

### Model Selection
If your tool supports multiple models:
```json
"model_arg": ["--model", "{model}"]
```

Then specify in agent config:
```json
"agents": {
    "architect": {
        "backend": "my-tool",
        "model": "gpt-4",
        "backend_config": { ... }
    }
}
```

## Full Documentation

See [docs/custom-backends.md](custom-backends.md) for complete documentation with examples and troubleshooting.
