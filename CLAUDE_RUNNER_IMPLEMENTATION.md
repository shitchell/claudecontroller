# Claude Runner Implementation

## Overview
The Claude Runner is a plugin for the claudecontroller system that manages Claude AI processes as long-running tasks. It provides robust process management, streaming output capture, and detailed analytics.

## Architecture

### Commands
1. **`runner`** - Launch a Claude process with specified prompt and options
2. **`runner-status`** - Get detailed status of Claude runners including metrics

### Key Features
- Context file support (prepended to prompts)
- Dual logging: streaming consciousness + final report
- Tool usage analytics
- Configurable default options
- Proper NVM environment handling

## Implementation Details

### 1. Runner Command (`commands/runner.py`)

#### Arguments
- `prompt` (required) - The prompt to send to Claude
- `--context-file` - File to prepend to the prompt
- `--report` - File path to request Claude write a report to
- `--name` - Custom name for the process
- `--model` - Claude model to use
- `--no-permissions` - Toggle dangerous permissions flag (default: True)

#### Fixed Options (not overridable)
- `--verbose` - Always enabled for stream parsing
- `--output-format stream-json` - Required for parsing output

#### Process Flow
1. Parse arguments and validate
2. Load context file if specified
3. Construct Claude command with proper environment
4. Start process with dual logging
5. Parse streaming JSON output
6. Track metrics and tool usage

### 2. Runner Status Command (`commands/runner_status.py`)

#### Features
- Show all Claude runners (running/stopped)
- Display metrics:
  - PID and duration
  - Tool call counts by type
  - Token usage statistics
  - Model information
  - Final status/error

### 3. Log Files

#### Stream Log (`logs/claude/{timestamp}_{name}_stream.jsonl`)
- Raw JSON stream from Claude
- One JSON object per line
- Includes all intermediate responses

#### Report Log (`logs/claude/{timestamp}_{name}_report.json`)
- Final summary with:
  - Total duration
  - Tool usage breakdown
  - Token counts
  - Final result/error
  - Cost estimation

## Configuration

### Default Settings (in config.json)
```json
{
  "claude_runner": {
    "dangerously_skip_permissions": true,
    "default_model": null,
    "node_setup": {
      "type": "auto",       // auto|nvm|asdf|fnm|volta|n|system|custom
      "nvm_dir": null,      // Custom NVM_DIR path
      "nvm_script": null,   // Path to nvm.sh or similar
      "node_path": null,    // Direct path to node binary
      "claude_path": null   // Direct path to claude binary
    }
  }
}
```

### Node Setup Types

1. **`auto`** (default) - Automatically detects your Node.js setup
2. **`nvm`** - Node Version Manager (most common)
3. **`asdf`** - asdf version manager with nodejs plugin
4. **`fnm`** - Fast Node Manager
5. **`volta`** - Volta (JavaScript tool manager)
6. **`n`** - n (Node.js version management)
7. **`system`** - System-installed Node.js (apt, brew, etc.)
8. **`custom`** - Manual configuration with explicit paths

### Example Configurations

#### Auto-detect (recommended)
```json
{
  "node_setup": {
    "type": "auto"
  }
}
```

#### Custom NVM installation
```json
{
  "node_setup": {
    "type": "nvm",
    "nvm_dir": "/opt/nvm",
    "nvm_script": "/opt/nvm/nvm.sh"
  }
}
```

#### Direct paths (no version manager)
```json
{
  "node_setup": {
    "type": "custom",
    "node_path": "/usr/local/bin/node",
    "claude_path": "/usr/local/bin/claude"
  }
}
```

## Implementation Steps

1. **Create runner.py**
   - Argument parsing with context file support
   - Claude command construction
   - Process management with NVM sourcing
   - Stream parsing and metrics collection

2. **Create runner_status.py**
   - Query runner processes from manager
   - Parse metrics from process info
   - Format detailed status output

3. **Update config.json.example**
   - Add claude_runner section
   - Document configurable options

4. **Testing**
   - Test basic prompt execution
   - Test context file loading
   - Test stream parsing
   - Test error handling

## Stream Parsing

The Claude stream output follows this pattern:
```json
{"type": "assistant", "message": {...}, "session_id": "..."}
{"type": "user", "message": {...}, "session_id": "..."}
{"type": "result", "subtype": "success", "cost_usd": ..., "result": "..."}
```

Key message types to parse:
- `assistant` messages with `tool_use` content
- `result` messages for final status
- Error messages for failure cases

## Error Handling

1. **Node/NVM Issues** - Ensure proper environment loading
2. **Stream Parsing** - Handle incomplete JSON gracefully
3. **Process Crashes** - Capture and report appropriately
4. **Permission Errors** - Clear messaging about --dangerously-skip-permissions

## Future Enhancements

1. **Conversation Management** - Support for continuing conversations
2. **Template System** - Predefined prompts and contexts
3. **Cost Tracking** - Aggregate cost reporting
4. **Performance Metrics** - Response time analytics
5. **Auto-retry** - Configurable retry on failures