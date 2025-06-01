# Claude Controller

A flexible process management system for running and monitoring long-running commands with plugin-based architecture.

## Features

- 🚀 **Easy Setup**: Just run `launch.sh` and it auto-creates the symlink
- 📌 **Unique Process Names**: PIDs automatically appended to prevent collisions
- 📊 **Rich Status Output**: Shows duration, exit codes, and process state
- 📝 **Automatic Logging**: All processes logged to timestamped files
- 🔌 **Plugin Architecture**: Drop Python files in `commands/` to add features
- 🎯 **Git-style CLI**: Global options before commands, command options after
- 🔄 **Hot Reload**: Restart manager to load new commands without losing processes

## Quick Start

```bash
# 1. Start the launch manager (auto-creates symlink)
.claudecontroller.d/launch.sh

# 2. In another terminal, use the controller
./claudecontroller list-commands
./claudecontroller bash 'npm test' --name my-tests
./claudecontroller bash-status
./claudecontroller bash-watch my-tests-12345
```

## Installation

1. Clone or copy the `.claudecontroller.d` directory to your project
2. Run `.claudecontroller.d/launch.sh`
3. That's it! The `claudecontroller` symlink is created automatically

## Architecture

```
.claudecontroller.d/
├── launch.sh           # Auto-setup & keeps manager running
├── launch-manager.py   # Socket server managing processes
├── claudecontroller    # CLI client
├── commands/           # Plugin commands directory
│   ├── bash.py        # Run bash commands
│   ├── bash_status.py # Check process status
│   ├── bash_watch.py  # Watch process output
│   └── bash_stop.py   # Stop processes
└── logs/              # Auto-created log directory
    ├── launch-manager_*.log
    └── bash/*.log
```

## Built-in Commands

### Core Commands
- `status` - Show all managed processes
- `list-commands` - List available commands
- `help <command>` - Show help for a command
- `restart-manager` - Restart the manager
- `shutdown` - Shutdown manager and all processes

### Bash Commands
- `bash '<command>' [--name <name>] [--no-log]` - Run a bash command
- `bash-status [name] [--all]` - Show process status with duration
- `bash-watch <name> [--lines N]` - Watch process output
- `bash-stop <name>` - Stop a process

## Examples

```bash
# Run tests with custom name
./claudecontroller bash 'npm test' --name unit-tests

# Check all processes
./claudecontroller bash-status
[unit-tests-12345] RUNNING (pid: 12345, 2m 30s)
  Log: 20240601_143022_unit-tests-12345.log
[e2e-tests-12346] SUCCESS (5m 15s)
  Log: 20240601_142515_e2e-tests-12346.log

# Watch output
./claudecontroller bash-watch unit-tests-12345 --lines 50

# Global options
./claudecontroller -v bash-status          # Verbose output
./claudecontroller --json list-commands    # JSON output
```

## Creating Custom Commands

Drop a Python file in `commands/` with a `command` function:

```python
"""
My custom command description
"""
import argparse

def get_parser():
    parser = argparse.ArgumentParser(
        prog='claudecontroller my-command',
        description='Does something cool'
    )
    parser.add_argument('target', help='What to operate on')
    parser.add_argument('--force', action='store_true')
    return parser

def command(manager, args):
    parser = get_parser()
    parsed = parser.parse_args(args)
    
    # Access manager.processes, manager.process_info, etc.
    return {
        'success': True,
        'message': f'Operated on {parsed.target}'
    }
```

## Process Naming

Processes get unique names by appending PIDs:
- `test` → `test-12345`
- `e2e` → `e2e-12346`

This prevents collisions when running multiple instances of the same command.

## Logging

- Manager logs: `.claudecontroller.d/logs/launch-manager_TIMESTAMP.log`
- Process logs: `.claudecontroller.d/logs/bash/TIMESTAMP_NAME-PID.log`
- Use `--no-log` to disable logging for specific commands

## Socket Location

The Unix socket is created at `.claudecontroller.d/claude_controller.sock` to support multiple projects on the same system.

## License

WTFPL - Do What The Fuck You Want To Public License