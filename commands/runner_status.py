"""
Show detailed status of Claude runner processes

Usage: claudecontroller runner-status [--json]

Shows:
  - PID and duration
  - Tool call counts
  - Token usage
  - Cost estimates
  - Final status
"""
import argparse
from datetime import datetime
from typing import Dict, Any
import json
import time
import os
from pathlib import Path
import subprocess

def get_parser():
    """Get argument parser for this command"""
    parser = argparse.ArgumentParser(
        prog='claudecontroller runner-status',
        description='Show detailed status of Claude runner processes'
    )
    parser.add_argument('--json', action='store_true', help='Output in JSON format')
    parser.add_argument('--name', help='Show status for specific runner only')
    return parser

def format_duration(seconds: float) -> str:
    """Format duration in human-readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"

def format_tool_counts(tool_counts: Dict[str, int]) -> str:
    """Format tool counts as a comma-separated list"""
    if not tool_counts:
        return "none"
    
    items = []
    for tool, count in sorted(tool_counts.items()):
        items.append(f"{count} {tool}")
    
    return ", ".join(items)

def get_last_stream_line(stream_log_path: str) -> tuple:
    """Get last line and modification time of stream log"""
    try:
        path = Path(stream_log_path)
        if not path.exists():
            return None, None
            
        # Get modification time
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        
        # Get last line using tail command (efficient for large files)
        result = subprocess.run(
            ['tail', '-n', '1', stream_log_path],
            capture_output=True, text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            last_line = result.stdout.strip()
            # Try to parse as JSON and extract meaningful info
            try:
                data = json.loads(last_line)
                # Extract the most relevant info based on type
                if data.get('type') == 'assistant':
                    content = data.get('message', {}).get('content', [])
                    if content and isinstance(content, list):
                        if content[0].get('type') == 'tool_use':
                            return f"[tool: {content[0].get('name', 'unknown')}]", mtime
                        elif content[0].get('type') == 'text':
                            text = content[0].get('text', '')[:80]
                            return f"[text: {text}...]" if len(text) >= 80 else f"[text: {text}]", mtime
                elif data.get('type') == 'user':
                    return "[tool result]", mtime
                elif data.get('type') == 'result':
                    return f"[{data.get('subtype', 'result')}]", mtime
                return f"[{data.get('type', 'unknown')}]", mtime
            except:
                # If not JSON, just show truncated line
                return last_line[:80] + "..." if len(last_line) > 80 else last_line, mtime
        
        return None, mtime
    except Exception:
        return None, None

def command(manager, args: list) -> Dict[str, Any]:
    """Show detailed status of Claude runners"""
    # Parse arguments
    parser = get_parser()
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        return {'success': False, 'error': 'Invalid arguments. Use "claudecontroller help runner-status" for usage.'}
    
    # Collect runner processes
    runners = {}
    for name, info in manager.process_info.items():
        if info.get('type') == 'claude':
            if parsed_args.name and not name.startswith(parsed_args.name):
                continue
            
            proc = manager.processes.get(name)
            
            # Calculate duration
            start_time = datetime.fromisoformat(info['started'])
            duration = (datetime.now() - start_time).total_seconds()
            
            # Check if still running
            is_running = False
            return_code = None
            if proc:
                proc.poll()
                if proc.returncode is None:
                    is_running = True
                else:
                    return_code = proc.returncode
            
            runner_info = {
                'pid': info['pid'],
                'status': 'running' if is_running else info.get('status', 'stopped'),
                'duration': duration,
                'duration_formatted': format_duration(duration),
                'started': info['started'],
                'prompt': info.get('prompt', 'N/A'),
                'context_file': info.get('context_file'),
                'report_file': info.get('report_data', {}).get('report_file'),
                'model': info.get('model', 'N/A'),
                'tool_counts': info.get('tool_counts', {}),
                'tool_counts_formatted': format_tool_counts(info.get('tool_counts', {})),
                'total_tokens': info.get('total_tokens', 0),
                'input_tokens': info.get('total_input_tokens', 0),
                'output_tokens': info.get('total_output_tokens', 0),
                'cost_usd': info.get('cost_usd', 0),
                'is_error': info.get('is_error', False),
                'return_code': return_code,
                'stream_log': info.get('stream_log'),
                'report_log': info.get('report_log')
            }
            
            # Add error info if available
            if 'error' in info:
                runner_info['error'] = info['error']
            
            runners[name] = runner_info
    
    if parsed_args.json:
        return {'success': True, 'runners': runners}
    
    # Format for display
    if not runners:
        return {'success': True, 'message': 'No Claude runners found'}
    
    output_lines = []
    output_lines.append("=== Claude Runner Status ===\n")
    
    for name, info in sorted(runners.items()):
        status_symbol = "●" if info['status'] == 'running' else "○"
        error_marker = " [ERROR]" if info['is_error'] else ""
        
        output_lines.append(f"{status_symbol} {name}{error_marker}")
        output_lines.append(f"  Status: {info['status']} (PID: {info['pid']})")
        output_lines.append(f"  Duration: {info['duration_formatted']}")
        output_lines.append(f"  Model: {info['model']}")
        
        # Show prompt preview
        prompt_preview = info['prompt'][:100] + "..." if len(info['prompt']) > 100 else info['prompt']
        prompt_preview = prompt_preview.replace('\n', ' ')
        output_lines.append(f"  Prompt: {prompt_preview}")
        
        if info['context_file']:
            output_lines.append(f"  Context: {info['context_file']}")
        
        if info['report_file']:
            output_lines.append(f"  Report: {info['report_file']}")
        
        # Tool usage
        if info['tool_counts']:
            output_lines.append(f"  Tools: {info['tool_counts_formatted']}")
        
        # Token usage
        if info['total_tokens'] > 0:
            output_lines.append(f"  Tokens: {info['total_tokens']:,} " +
                              f"(in: {info['input_tokens']:,}, out: {info['output_tokens']:,})")
        
        # Cost
        if info['cost_usd'] > 0:
            output_lines.append(f"  Cost: ${info['cost_usd']:.4f}")
        
        # Error info
        if 'error' in info:
            output_lines.append(f"  Error: {info['error']}")
        
        # For running processes, show last activity
        if info['status'] == 'running' and info['stream_log']:
            last_line, mtime = get_last_stream_line(info['stream_log'])
            if last_line:
                output_lines.append(f"  Last activity: {last_line}")
            if mtime:
                time_ago = format_duration((datetime.now() - mtime).total_seconds())
                output_lines.append(f"  Last update: {time_ago} ago")
        
        # Log files
        if info['stream_log']:
            stream_name = info['stream_log'].split('/')[-1] if '/' in info['stream_log'] else info['stream_log']
            output_lines.append(f"  Stream log: {stream_name}")
        
        if info['report_log']:
            report_name = info['report_log'].split('/')[-1] if '/' in info['report_log'] else info['report_log']
            output_lines.append(f"  Report log: {report_name}")
        
        output_lines.append("")
    
    return {'success': True, 'message': '\n'.join(output_lines)}