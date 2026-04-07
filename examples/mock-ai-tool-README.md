# Mock AI Tool

A simple mock CLI tool for testing custom backend integration with the agent coordinator.

## Usage

```bash
# Text output (default)
./mock-ai-tool run "Your prompt here" --dir /path/to/workspace

# JSON output
./mock-ai-tool run "Your prompt here" --dir /path/to/workspace --format json

# JSONL output (streaming)
./mock-ai-tool run "Your prompt here" --dir /path/to/workspace --format jsonl

# With session continuity
./mock-ai-tool run "Your prompt here" --session abc123

# With model selection
./mock-ai-tool run "Your prompt here" --model gpt-4
```

## Testing with Agent Coordinator

Create a test agents.json:

```json
{
    "default_backend": "mock",
    "agents": {
        "architect": {
            "backend": "mock",
            "backend_config": {
                "command": ["./examples/mock-ai-tool", "run", "--format", "json"],
                "message_arg": "{message}",
                "workspace_arg": ["--dir", "{workspace}"],
                "session_arg": ["--session", "{session_id}"],
                "model_arg": ["--model", "{model}"],
                "output_format": "json",
                "json_text_field": "result",
                "json_session_field": "session_id"
            },
            "prompt_file": "prompts/architect.md"
        }
    }
}
```

Then run:
```bash
agent-coordinator --workspace /path/to/test --max-turns 3
```

## Output Formats

### Text
```
I received the prompt: Your prompt here...
Working in directory: /path/to/workspace
Using session: abc123
Model: default

Mock analysis complete. Would update handoff.md here.
```

### JSON
```json
{
    "result": "I received the prompt: Your prompt here...\nWorking in directory: /path/to/workspace\n...",
    "session_id": "abc123",
    "status": "success"
}
```

### JSONL (Streaming)
```jsonl
{"sessionID": "abc123", "type": "init"}
{"type": "text", "part": {"text": "I received the prompt: Your prompt here...\n"}}
{"type": "text", "part": {"text": "Working in directory: /path/to/workspace\n"}}
{"type": "complete", "sessionID": "abc123"}
```

## Purpose

This tool demonstrates:
- How to create a CLI tool compatible with the agent coordinator
- Different output format options (text, json, jsonl)
- Session/context management
- Model selection
- Workspace integration

Use it as a reference when building your own custom backend CLI tool.
