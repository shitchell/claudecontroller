"""
Execute a bash command as a managed process

Usage: claudecontroller bash '<command>' [--name <process_name>]

Examples:
  claudecontroller bash 'npm run dev'
  claudecontroller bash 'npm test -- --watch' --name test-watch
  claudecontroller bash 'npx playwright install' --name playwright-install
"""
import subprocess
import argparse
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
import os

def get_parser():
    """Get argument parser for this command"""
    parser = argparse.ArgumentParser(
        prog='claudecontroller bash',
        description='Execute a bash command as a managed process'
    )
    parser.add_argument('command', help='Bash command to execute')
    parser.add_argument('--name', '-n', help='Process name (auto-generated if not specified)')
    parser.add_argument('--no-log', action='store_true', help='Disable logging to file')
    return parser

def command(manager, args: list) -> Dict[str, Any]:
    """Execute a bash command as a managed process"""
    # Parse arguments
    parser = get_parser()
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        # argparse tries to exit on error, capture the help text
        return {'success': False, 'error': 'Invalid arguments. Use "claudecontroller help bash" for usage.'}
    
    bash_command = parsed_args.command
    base_name = parsed_args.name
    
    # Start the process first to get PID
    try:
        # Set up logging
        log_dir = Path(__file__).parent.parent / 'logs' / 'bash'
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Start the process
        if parsed_args.no_log:
            proc = subprocess.Popen(
                bash_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
        else:
            # Create log file with timestamp and PID (will be updated with actual PID)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_log_name = f"{timestamp}_temp.log"
            log_file_path = log_dir / temp_log_name
            log_file = open(log_file_path, 'w')
            
            proc = subprocess.Popen(
                bash_command,
                shell=True,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
        
        # Now we have the PID, create the process name
        if not base_name:
            # Generate a name from command
            cmd_prefix = bash_command.split()[0].split('/')[-1][:10]
            base_name = f"bash-{cmd_prefix}"
        
        # Append PID to make it unique
        process_name = f"{base_name}-{proc.pid}"
        
        # Rename log file with actual process name
        if not parsed_args.no_log:
            final_log_name = f"{timestamp}_{process_name}.log"
            final_log_path = log_dir / final_log_name
            log_file_path.rename(final_log_path)
            
            # Write header to log
            log_file.write(f"=== Process: {process_name} ===\n")
            log_file.write(f"Command: {bash_command}\n")
            log_file.write(f"Started: {datetime.now().isoformat()}\n")
            log_file.write(f"PID: {proc.pid}\n")
            log_file.write("=" * 50 + "\n")
            log_file.flush()
        
        # Store process info
        manager.processes[process_name] = proc
        manager.process_info[process_name] = {
            'command': bash_command,
            'started': datetime.now().isoformat(),
            'type': 'bash',
            'pid': proc.pid,
            'base_name': base_name,
            'log_file': str(final_log_path) if not parsed_args.no_log else None
        }
        
        return {
            'success': True,
            'pid': proc.pid,
            'name': process_name,
            'message': f'Started bash process "{process_name}" with PID {proc.pid}' +
                      (f'\nLog file: {final_log_path.name}' if not parsed_args.no_log else '')
        }
        
    except Exception as e:
        return {'success': False, 'error': f'Failed to start process: {str(e)}'}