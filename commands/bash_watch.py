"""
Watch output of a bash process

Usage: claudecontroller bash-watch <process_name> [--lines <n>]

Shows the recent output from a bash process. By default shows last 50 lines.
"""
import subprocess
import argparse
from typing import Dict, Any
from collections import deque

# Global output buffers for each process
OUTPUT_BUFFERS = {}

def get_parser():
    """Get argument parser for this command"""
    parser = argparse.ArgumentParser(
        prog='claudecontroller bash-watch',
        description='Watch output from a bash process'
    )
    parser.add_argument('name', help='Name of the process to watch')
    parser.add_argument('--lines', '-l', type=int, default=50, 
                       help='Number of lines to show (default: 50)')
    return parser

def command(manager, args: list) -> Dict[str, Any]:
    """Watch output of a bash process"""
    # Parse arguments
    parser = get_parser()
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        return {'success': False, 'error': 'Invalid arguments. Use "claudecontroller help bash-watch" for usage.'}
    
    process_name = parsed_args.name
    num_lines = parsed_args.lines
    
    # Check if process exists
    if process_name not in manager.processes:
        return {'success': False, 'error': f'Process "{process_name}" not found'}
    
    proc = manager.processes[process_name]
    proc.poll()
    
    if proc.returncode is not None:
        return {
            'success': True,
            'output': f'Process "{process_name}" has stopped with return code {proc.returncode}'
        }
    
    # Initialize buffer if needed
    if process_name not in OUTPUT_BUFFERS:
        OUTPUT_BUFFERS[process_name] = deque(maxlen=1000)
    
    buffer = OUTPUT_BUFFERS[process_name]
    
    # Read available output
    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            buffer.append(line.rstrip())
    except:
        pass
    
    # Get requested lines
    output_lines = list(buffer)[-num_lines:]
    
    if output_lines:
        output = '\n'.join(output_lines)
        return {
            'success': True,
            'output': f'=== Output from {process_name} (last {len(output_lines)} lines) ===\n{output}'
        }
    else:
        return {
            'success': True,
            'output': f'No output yet from process "{process_name}"'
        }