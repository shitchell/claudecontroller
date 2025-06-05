"""
Show token usage for the current Claude Code conversation
"""
import argparse
import json
import os
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def get_parser():
    parser = argparse.ArgumentParser(
        prog='claudecontroller tokens',
        description='Show token usage for the current Claude Code conversation'
    )
    parser.add_argument('--json', action='store_true',
                       help='Output in JSON format')
    parser.add_argument('--todos', action='store_true',
                       help='Analyze token usage across todo items')
    parser.add_argument('-n', '--sessions', type=int, default=1, metavar='N',
                       help='Number of recent sessions to analyze (default: 1)')
    return parser


def sanitize_path_for_claude(path):
    """Convert a filesystem path to Claude's project directory format"""
    # Replace all non-alphanumeric characters with dashes
    sanitized = re.sub(r'[^a-zA-Z0-9]', '-', path)
    # Collapse multiple consecutive dashes (Claude seems to do some collapsing)
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized


def get_claude_project_dir(cwd):
    """Get the Claude project directory for the current working directory"""
    dir_component = sanitize_path_for_claude(cwd)
    return Path.home() / '.claude' / 'projects' / dir_component


def find_latest_stream_file(cwd):
    """Find the most recently modified .jsonl file for the current directory"""
    claude_dir = get_claude_project_dir(cwd)
    
    if not claude_dir.exists():
        return None
    
    # Find all .jsonl files and get the most recent
    jsonl_files = list(claude_dir.glob('*.jsonl'))
    if not jsonl_files:
        return None
    
    return max(jsonl_files, key=lambda f: f.stat().st_mtime)


def get_recent_stream_files(cwd, n=1):
    """Get the N most recently modified .jsonl files for the current directory"""
    claude_dir = get_claude_project_dir(cwd)
    
    if not claude_dir.exists():
        return []
    
    # Find all .jsonl files and sort by modification time (newest first)
    jsonl_files = list(claude_dir.glob('*.jsonl'))
    jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    return jsonl_files[:n]


def parse_line_for_todo_event(line_data):
    """Extract todo event from a parsed JSON line"""
    message = line_data.get('message', {})
    content = message.get('content', [])
    
    if not isinstance(content, list):
        return None
    
    for item in content:
        if (isinstance(item, dict) and 
            item.get('type') == 'tool_use' and 
            item.get('name') == 'TodoWrite'):
            
            tool_input = item.get('input', {})
            todos = tool_input.get('todos', [])
            usage = message.get('usage', {})
            
            return {
                'todos': todos,
                'usage': usage,
                'total_tokens': calculate_total_tokens(usage)
            }
    
    return None


def calculate_total_tokens(usage):
    """Calculate total tokens from usage dict"""
    return (
        usage.get('input_tokens', 0) +
        usage.get('cache_creation_input_tokens', 0) +
        usage.get('cache_read_input_tokens', 0)
    )


def parse_session_todos(stream_file):
    """Parse all todo events from a single session file"""
    todo_events = []
    
    try:
        with open(stream_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    timestamp = data.get('timestamp')
                    if not timestamp:
                        continue
                    
                    todo_event = parse_line_for_todo_event(data)
                    if todo_event:
                        todo_events.append({
                            'timestamp': timestamp,
                            'line': line_num,
                            'todos': todo_event['todos'],
                            'total_tokens': todo_event['total_tokens'],
                            'usage': todo_event['usage']
                        })
                except json.JSONDecodeError:
                    continue
    except (FileNotFoundError, IOError):
        pass
    
    return sorted(todo_events, key=lambda x: x['timestamp'])


def track_todo_lifecycle(todo_events):
    """Track todo lifecycle from in_progress to completed"""
    # Use content as key instead of ID to handle ID reuse
    todo_tracking = {}
    
    for event in todo_events:
        event_time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        
        for todo in event['todos']:
            todo_id = todo.get('id')
            todo_content = todo.get('content', 'Unknown task')
            todo_status = todo.get('status', 'unknown')
            
            # Use content as the key
            if todo_content not in todo_tracking:
                todo_tracking[todo_content] = {
                    'id': todo_id,  # Keep ID for reference
                    'in_progress_event': None,
                    'completed_event': None,
                    'status': todo_status,
                    'all_events': []  # Track all events for debugging
                }
            
            # Track all events for this todo
            todo_tracking[todo_content]['all_events'].append({
                'timestamp': event_time,
                'status': todo_status,
                'tokens': event['total_tokens']
            })
            
            # Track when todo goes in_progress
            if (todo_status == 'in_progress' and 
                todo_tracking[todo_content]['in_progress_event'] is None):
                todo_tracking[todo_content]['in_progress_event'] = {
                    'timestamp': event_time,
                    'tokens': event['total_tokens']
                }
            
            # Track when todo is completed AFTER being in_progress
            if (todo_status == 'completed' and 
                todo_tracking[todo_content]['in_progress_event'] is not None and
                todo_tracking[todo_content]['completed_event'] is None):
                todo_tracking[todo_content]['completed_event'] = {
                    'timestamp': event_time,
                    'tokens': event['total_tokens']
                }
            
            # Update latest status and ID
            todo_tracking[todo_content]['status'] = todo_status
            todo_tracking[todo_content]['id'] = todo_id  # Update ID in case it changed
    
    return todo_tracking


def calculate_todo_metrics(todo_tracking):
    """Calculate token usage metrics for todos"""
    todo_metrics = {}
    
    for todo_content, tracking in todo_tracking.items():
        in_progress = tracking['in_progress_event']
        completed = tracking['completed_event']
        todo_id = tracking['id']
        
        if in_progress and completed:
            # Calculate from in_progress to completed
            token_delta = completed['tokens'] - in_progress['tokens']
            if token_delta >= 0:  # Skip negative deltas
                duration = completed['timestamp'] - in_progress['timestamp']
                todo_metrics[todo_content] = {
                    'id': todo_id,
                    'started_at': in_progress['timestamp'],
                    'completed_at': completed['timestamp'],
                    'status': 'completed',
                    'total_tokens': token_delta,
                    'duration': duration
                }
        elif in_progress and not completed:
            # Todo still in progress
            todo_metrics[todo_content] = {
                'id': todo_id,
                'started_at': in_progress['timestamp'],
                'completed_at': None,
                'status': 'in_progress',
                'total_tokens': None,  # Unknown until completed
                'duration': None
            }
        else:
            # Unknown - doesn't have proper in_progress -> completed flow
            todo_metrics[todo_content] = {
                'id': todo_id,
                'started_at': None,
                'completed_at': None,
                'status': 'unknown',
                'total_tokens': None,
                'duration': None,
                'all_events': tracking['all_events']  # Include for debugging
            }
    
    return todo_metrics


def analyze_sessions_todos(stream_files):
    """Analyze todo token usage grouped by session"""
    sessions_analysis = {}
    
    for stream_file in stream_files:
        session_id = stream_file.stem
        todo_events = parse_session_todos(stream_file)
        
        if todo_events:
            todo_tracking = track_todo_lifecycle(todo_events)
            todo_metrics = calculate_todo_metrics(todo_tracking)
            
            sessions_analysis[session_id] = {
                'file': str(stream_file),
                'todos': todo_metrics,
                'event_count': len(todo_events)
            }
    
    return sessions_analysis


def format_session_todos(session_id, session_data):
    """Format todo output for a single session"""
    output = []
    output.append(f"\n📂 Session: {session_id}")
    output.append("=" * 60)
    
    todos = session_data['todos']
    if not todos:
        output.append("No todos found in this session.")
        return output
    
    # Sort todos: first by started_at (if available), then unknowns at the end
    todos_with_start = [(k, v) for k, v in todos.items() if v['started_at'] is not None]
    todos_without_start = [(k, v) for k, v in todos.items() if v['started_at'] is None]
    
    sorted_todos = (
        sorted(todos_with_start, key=lambda x: x[1]['started_at']) +
        sorted(todos_without_start, key=lambda x: x[0])  # Sort unknowns by content
    )
    
    for todo_content, metrics in sorted_todos:
        if metrics['status'] == 'completed':
            status_emoji = "✅"
        elif metrics['status'] == 'in_progress':
            status_emoji = "⏳"
        else:
            status_emoji = "❓"
        
        output.append(f"{status_emoji} {todo_content}")
        output.append(f"   ID: {metrics['id']}")
        output.append(f"   Status: {metrics['status']}")
        
        if metrics['total_tokens'] is not None:
            output.append(f"   Tokens: {metrics['total_tokens']:,}")
        elif metrics['status'] == 'in_progress':
            output.append(f"   Tokens: In progress...")
        else:
            output.append(f"   Tokens: Unknown (no proper flow)")
        
        if metrics['duration']:
            duration_str = str(metrics['duration']).split('.')[0]
            output.append(f"   Duration: {duration_str}")
        
        output.append("")
    
    # Session summary
    completed_todos = [t for t in todos.values() if t['status'] == 'completed' and t['total_tokens'] is not None]
    if completed_todos:
        total_tokens = sum(t['total_tokens'] for t in completed_todos)
        avg_tokens = total_tokens / len(completed_todos)
        
        output.append("📊 Session Summary")
        output.append("-" * 20)
        output.append(f"Total todos: {len(todos)}")
        output.append(f"Completed: {len(completed_todos)}")
        output.append(f"Total tokens: {total_tokens:,}")
        output.append(f"Avg tokens per completed: {avg_tokens:,.0f}")
    
    return output


def format_todos_output(sessions_analysis, json_output=False):
    """Format the todo analytics output"""
    if not sessions_analysis:
        return "No todo data found in the selected sessions."
    
    if json_output:
        # Convert datetime objects to strings for JSON serialization
        serializable = {}
        for session_id, session_data in sessions_analysis.items():
            serializable[session_id] = {
                'file': session_data['file'],
                'event_count': session_data['event_count'],
                'todos': {}
            }
            for todo_content, metrics in session_data['todos'].items():
                serializable[session_id]['todos'][todo_content] = {
                    'id': metrics.get('id'),
                    'started_at': metrics['started_at'].isoformat() if metrics['started_at'] else None,
                    'completed_at': metrics['completed_at'].isoformat() if metrics['completed_at'] else None,
                    'status': metrics['status'],
                    'total_tokens': metrics['total_tokens'],
                    'duration_seconds': metrics['duration'].total_seconds() if metrics['duration'] else None
                }
        return json.dumps(serializable, indent=2)
    
    # Human-readable format
    output = ["📋 Todo Token Analysis"]
    
    # Sort sessions by file modification time (newest first)
    sorted_sessions = sorted(
        sessions_analysis.items(),
        key=lambda x: Path(x[1]['file']).stat().st_mtime,
        reverse=True
    )
    
    for session_id, session_data in sorted_sessions:
        output.extend(format_session_todos(session_id, session_data))
    
    return "\n".join(output)


def get_token_usage(stream_file):
    """Extract token usage from the last line of a Claude stream file"""
    try:
        with open(stream_file, 'r') as f:
            # Read the last line
            lines = f.readlines()
            if not lines:
                return None
            
            last_line = lines[-1].strip()
            data = json.loads(last_line)
            
            # Extract usage from the message
            usage = data.get('message', {}).get('usage', {})
            return usage
    except (json.JSONDecodeError, FileNotFoundError, KeyError):
        return None


def calculate_context_stats(usage):
    """Calculate context window statistics"""
    if not usage:
        return None
    
    # Get token counts
    input_tokens = usage.get('input_tokens', 0)
    cache_creation_tokens = usage.get('cache_creation_input_tokens', 0)
    cache_read_tokens = usage.get('cache_read_input_tokens', 0)
    output_tokens = usage.get('output_tokens', 0)
    
    # Calculate total context (input + cache)
    total_context = input_tokens + cache_creation_tokens + cache_read_tokens
    
    # Claude model limits
    context_window = 200000
    claude_code_cutoff = 165000
    
    # Calculate remaining
    remaining_tokens = claude_code_cutoff - total_context
    usage_percentage = (total_context / claude_code_cutoff) * 100
    remaining_percentage = 100 - usage_percentage
    
    return {
        'input_tokens': input_tokens,
        'cache_creation_tokens': cache_creation_tokens,
        'cache_read_tokens': cache_read_tokens,
        'output_tokens': output_tokens,
        'total_context_tokens': total_context,
        'context_window': context_window,
        'claude_code_cutoff': claude_code_cutoff,
        'remaining_tokens': remaining_tokens,
        'usage_percentage': usage_percentage,
        'remaining_percentage': remaining_percentage
    }


def format_token_stats(stats, json_output=False):
    """Format the token usage output"""
    if not stats:
        return "No token usage data found for current conversation."
    
    if json_output:
        return json.dumps(stats, indent=2)
    
    # Human-readable format
    output = []
    output.append("🔤 Token Usage")
    output.append("=" * 40)
    output.append(f"Input tokens (current):     {stats['input_tokens']:,}")
    output.append(f"Cache creation tokens:      {stats['cache_creation_tokens']:,}")
    output.append(f"Cache read tokens:          {stats['cache_read_tokens']:,}")
    output.append(f"Output tokens:              {stats['output_tokens']:,}")
    output.append(f"Total context tokens:       {stats['total_context_tokens']:,}")
    output.append("")
    output.append("📊 Context Window")
    output.append("=" * 40)
    output.append(f"Model context window:       {stats['context_window']:,}")
    output.append(f"Claude Code cutoff:         {stats['claude_code_cutoff']:,}")
    output.append(f"Remaining tokens:           {stats['remaining_tokens']:,}")
    output.append(f"Usage:                      {stats['usage_percentage']:.1f}%")
    output.append(f"Remaining:                  {stats['remaining_percentage']:.1f}%")
    
    return "\n".join(output)


def command(manager, args):
    parser = get_parser()
    parsed = parser.parse_args(args)
    
    # Get current working directory
    cwd = os.getcwd()
    
    if parsed.todos:
        # Todo analysis mode
        stream_files = get_recent_stream_files(cwd, parsed.sessions)
        if not stream_files:
            return {
                'success': False,
                'message': 'No Claude Code conversations found for this directory'
            }
        
        # Analyze todos by session
        sessions_analysis = analyze_sessions_todos(stream_files)
        
        # Format output
        output = format_todos_output(sessions_analysis, parsed.json)
        
        return {
            'success': True,
            'message': output
        }
    else:
        # Regular token usage mode
        stream_file = find_latest_stream_file(cwd)
        if not stream_file:
            return {
                'success': False,
                'message': 'No Claude Code conversation found for this directory'
            }
        
        # Get token usage
        usage = get_token_usage(stream_file)
        stats = calculate_context_stats(usage)
        
        # Format output
        output = format_token_stats(stats, parsed.json)
        
        return {
            'success': True,
            'message': output
        }
