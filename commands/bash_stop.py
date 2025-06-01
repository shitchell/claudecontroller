"""
Stop a bash process

Usage: claudecontroller bash-stop <process_name>

Stops a running bash process by name.
"""
from typing import Dict, Any

def command(manager, args: list) -> Dict[str, Any]:
    """Stop a bash process"""
    if not args:
        return {'success': False, 'error': 'No process name specified'}
    
    process_name = args[0]
    
    # Check if process exists
    if process_name not in manager.processes:
        return {'success': False, 'error': f'Process "{process_name}" not found'}
    
    # Check if it's a bash process
    if manager.process_info.get(process_name, {}).get('type') != 'bash':
        return {'success': False, 'error': f'"{process_name}" is not a bash process'}
    
    # Stop the process
    manager.stop_process(process_name)
    
    return {
        'success': True,
        'message': f'Stopped bash process "{process_name}"'
    }