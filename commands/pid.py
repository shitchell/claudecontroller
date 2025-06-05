"""
Show the PID of the running ClaudeController manager
"""
import argparse
import os
from pathlib import Path


def get_parser():
    parser = argparse.ArgumentParser(
        prog='claudecontroller pid',
        description='Show the PID of the running ClaudeController manager'
    )
    parser.add_argument('--json', action='store_true',
                       help='Output in JSON format')
    return parser


def get_manager_pid():
    """Get manager PID from .pid file or return None if not found"""
    pid_file = Path('.pid')
    
    if not pid_file.exists():
        return None
    
    try:
        with open(pid_file, 'r') as f:
            pid_str = f.read().strip()
            if pid_str:
                pid = int(pid_str)
                # Verify process is actually running
                try:
                    os.kill(pid, 0)  # Signal 0 checks if process exists
                    return pid
                except (OSError, ProcessLookupError):
                    # Process doesn't exist, clean up stale pid file
                    pid_file.unlink(missing_ok=True)
                    return None
            return None
    except (ValueError, IOError):
        # Invalid or unreadable pid file
        pid_file.unlink(missing_ok=True)
        return None


def command(manager, args):
    parser = get_parser()
    parsed = parser.parse_args(args)
    
    pid = get_manager_pid()
    
    if pid is None:
        return {
            'success': False,
            'message': 'No manager PID found or manager not running'
        }
    
    if parsed.json:
        import json
        return {
            'success': True,
            'message': json.dumps({'pid': pid}, indent=2)
        }
    else:
        return {
            'success': True,
            'message': str(pid)
        }