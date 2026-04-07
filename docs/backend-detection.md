# Backend Auto-Detection

The coordinator now automatically detects backend executables and gracefully handles missing backends.

## How It Works

### 1. Check Registry

First checks if backend is in the built-in registry:
- `claude` - Claude CLI
- `copilot` - GitHub Copilot CLI
- `manual` - Manual runner
- `opencode` - OpenCode backend

### 2. Check PATH

If not in registry, uses `which <backend>` to find executable:

```bash
$ which copilot
/Users/username/.nvm/versions/node/v22.14.0/bin/copilot

$ which claude
/opt/homebrew/bin/claude

$ which codex
/opt/homebrew/bin/codex
```

If found, creates automatic configuration:
```json
{
  "executable": "/path/to/backend",
  "args": ["--workspace", "{workspace}"]
}
```

### 3. Prompt User

If executable not found in PATH, prompts user:

```
Backend 'mybackend' not found in supported backends and executable not in PATH.

Supported backends: claude, copilot, manual, opencode

You can:
  1. Provide the full path to the backend executable
  2. Update agents.json to use a supported backend
  3. Add 'backend_config' in agents.json for this backend

Enter path to backend executable (or press Enter to abort):
```

User can:
- Enter full path: `/usr/local/bin/mybackend`
- Press Enter to abort and fix agents.json

### 4. Use backend_config

If `backend_config` is provided in agents.json, uses that directly:

```json
{
  "agents": {
    "custom_agent": {
      "backend": "mybackend",
      "backend_config": {
        "executable": "/custom/path/to/mybackend",
        "args": ["--custom-arg", "{workspace}"]
      }
    }
  }
}
```

## Examples

### Example 1: Built-in Backend

```json
{
  "agents": {
    "architect": {
      "backend": "copilot",
      "model": "claude-sonnet-4.5"
    }
  }
}
```

✓ Works immediately (copilot in registry)

### Example 2: Executable in PATH

```json
{
  "agents": {
    "architect": {
      "backend": "codex",
      "model": "gpt-4"
    }
  }
}
```

✓ Auto-detects `codex` executable via `which`
✓ Creates config automatically

### Example 3: Custom Path

```json
{
  "agents": {
    "architect": {
      "backend": "myai",
      "backend_config": {
        "executable": "/home/user/myai/bin/myai",
        "args": ["--workspace", "{workspace}", "--verbose"]
      }
    }
  }
}
```

✓ Uses exact path specified

### Example 4: Not Found - Interactive

```json
{
  "agents": {
    "architect": {
      "backend": "notfound"
    }
  }
}
```

Prompts:
```
Backend 'notfound' not found...
Enter path to backend executable: /usr/local/bin/notfound
✓ Using backend at: /usr/local/bin/notfound
```

## Configuration Precedence

1. **Explicit backend_config** - Highest priority
2. **Registry** - Built-in backends
3. **PATH search** - Auto-detect via `which`
4. **User prompt** - Interactive fallback
5. **Error** - If user aborts

## Benefits

### Before

```
ValueError: Unknown backend: 'codex'. Supported: claude, copilot...
[Coordinator crashes]
```

User must:
1. Kill process
2. Edit agents.json
3. Restart coordinator

### After

```
Found codex executable at: /opt/homebrew/bin/codex
[Continues running]
```

Or if not found:
```
Backend 'codex' not found...
Enter path: /custom/path/codex
✓ Using backend at: /custom/path/codex
[Continues running]
```

No crash, no restart needed!

## Supported Patterns

### Pattern 1: All Same Backend

```json
{
  "default_backend": "copilot",
  "agents": {
    "architect": {},
    "developer": {},
    "qa_engineer": {}
  }
}
```

All use copilot.

### Pattern 2: Mixed Backends

```json
{
  "default_backend": "copilot",
  "agents": {
    "architect": {
      "backend": "claude"
    },
    "developer": {
      "backend": "copilot"
    },
    "helper": {
      "backend": "claude"
    }
  }
}
```

Mix and match backends per agent.

### Pattern 3: Custom Executables

```json
{
  "agents": {
    "specialist": {
      "backend": "custom",
      "backend_config": {
        "executable": "/opt/myai/bin/specialist",
        "args": ["--mode", "expert", "--workspace", "{workspace}"]
      }
    }
  }
}
```

Full control over execution.

## Troubleshooting

### Backend Not Found

**Symptom**: 
```
Backend 'xyz' not found in supported backends and executable not in PATH.
```

**Solutions**:

1. **Add to PATH**:
   ```bash
   export PATH="/path/to/backend/bin:$PATH"
   ```

2. **Use full path in agents.json**:
   ```json
   {
     "backend": "xyz",
     "backend_config": {
       "executable": "/full/path/to/xyz"
     }
   }
   ```

3. **Switch to supported backend**:
   ```json
   {
     "backend": "copilot"
   }
   ```

### Wrong Executable Found

**Symptom**: `which` finds wrong version

**Solution**: Use explicit path
```json
{
  "backend_config": {
    "executable": "/correct/path/to/backend"
  }
}
```

### Backend Requires Special Args

**Solution**: Provide full config
```json
{
  "backend_config": {
    "executable": "/path/to/backend",
    "args": ["--special-flag", "--workspace", "{workspace}"]
  }
}
```

## Environment Variables

Backends may use environment variables:

```bash
# Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# OpenAI
export OPENAI_API_KEY="sk-..."

# Custom
export CUSTOM_BACKEND_TOKEN="..."
```

The coordinator doesn't manage these - set them before running.

## Checking Backends

```bash
# Check what's available
which copilot
which claude
which codex

# Test a backend
copilot --help
claude --version

# Show PATH
echo $PATH
```

## Migration Guide

### Old agents.json (would crash)

```json
{
  "agents": {
    "architect": {
      "backend": "gpt5"
    }
  }
}
```

### New agents.json (auto-detects or prompts)

```json
{
  "agents": {
    "architect": {
      "backend": "copilot",
      "model": "claude-sonnet-4.5"
    }
  }
}
```

Or keep same and let it auto-detect if `gpt5` is in PATH!

## Best Practices

1. **Use built-in backends when possible** (claude, copilot)
2. **Add custom backends to PATH** for automatic detection
3. **Use backend_config** for complex setups
4. **Test backends before running workflow**:
   ```bash
   which mybackend
   mybackend --help
   ```

5. **Document custom backends** in your project README

The coordinator is now backend-agnostic and handles missing backends gracefully!
