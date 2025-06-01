"""
Check status of bash processes

Usage: claudecontroller bash-status [<process_name>]

Shows status of bash processes with duration and exit codes.
If no name is specified, shows all bash processes.
"""
import argparse
from typing import Dict, Any
from datetime import datetime

def get_parser():
    """Get argument parser for this command"""
    parser = argparse.ArgumentParser(
        prog='claudecontroller bash-status',
        description='Check status of bash processes'
    )
    parser.add_argument('name', nargs='?', help='Name of the process (optional, shows all if omitted)')
    parser.add_argument('--all', '-a', action='store_true', help='Show all processes, not just bash')
    return parser

def format_duration(start_time_str: str, end_time_str: str = None) -> str:
    """Format duration in human-readable form"""
    try:
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str) if end_time_str else datetime.now()
        duration = end_time - start_time
        
        # Format duration
        total_seconds = int(duration.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    except:
        return "unknown"

def command(manager, args: list) -> Dict[str, Any]:
    """Check status of bash processes"""
    # Parse arguments
    parser = get_parser()
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        return {'success': False, 'error': 'Invalid arguments. Use "claudecontroller help bash-status" for usage.'}
    
    target_name = parsed_args.name
    show_all = parsed_args.all
    
    status = {}
    for name, info in manager.process_info.items():
        # Filter for bash processes unless --all
        if not show_all and info.get('type') != 'bash':
            continue
            
        # Filter by name if specified
        if target_name and name != target_name:
            continue
            
        proc = manager.processes.get(name)
        if proc:
            proc.poll()
            if proc.returncode is None:
                # Still running
                duration = format_duration(info['started'])
                status[name] = {
                    'status': 'running',
                    'pid': proc.pid,
                    'command': info['command'],
                    'started': info['started'],
                    'duration': duration,
                    'base_name': info.get('base_name', name),
                    'log_file': info.get('log_file')
                }
            else:
                # Process ended
                end_time = info.get('ended', datetime.now().isoformat())
                duration = format_duration(info['started'], end_time)
                status[name] = {
                    'status': 'exited',
                    'exit_code': proc.returncode,
                    'command': info['command'],
                    'started': info['started'],
                    'ended': end_time,
                    'duration': duration,
                    'base_name': info.get('base_name', name),
                    'log_file': info.get('log_file')
                }
                # Update ended time if not set
                if 'ended' not in info:
                    info['ended'] = end_time
        else:
            status[name] = {
                'status': 'not started',
                'command': info['command'],
                'base_name': info.get('base_name', name)
            }
    
    if target_name and not status:
        return {'success': False, 'error': f'No {"" if show_all else "bash "}process found with name: {target_name}'}
    
    # Custom formatting for status output
    if status:
        output_lines = []
        for name, proc_info in sorted(status.items()):
            proc_status = proc_info['status']
            base_name = proc_info.get('base_name', name)
            
            if proc_status == 'running':
                line = f"[{name}] RUNNING (pid: {proc_info['pid']}, {proc_info['duration']})"
            elif proc_status == 'exited':
                exit_code = proc_info['exit_code']
                exit_status = "SUCCESS" if exit_code == 0 else f"FAILED ({exit_code})"
                line = f"[{name}] {exit_status} ({proc_info['duration']})"
            else:
                line = f"[{name}] NOT STARTED"
            
            output_lines.append(line)
            
            # Add command info in verbose mode (check parent context)
            if proc_info.get('log_file'):
                output_lines.append(f"  Log: {proc_info['log_file'].split('/')[-1]}")
        
        return {
            'success': True,
            'output': '\n'.join(output_lines),
            '_raw_status': status  # Keep raw data for JSON output
        }
    else:
        return {
            'success': True,
            'output': f'No {"" if show_all else "bash "}processes found'
        }