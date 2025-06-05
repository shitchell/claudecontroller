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
    parser.add_argument('--tasks', action='store_true',
                       help='Analyze token usage across task chains (using isSidechain)')
    parser.add_argument('--all', action='store_true',
                       help='Analyze both tasks and todos in unified view')
    parser.add_argument('--brief', action='store_true',
                       help='Show concise output format')
    parser.add_argument('-n', '--sessions', type=int, default=1, metavar='N',
                       help='Number of recent sessions to analyze (default: 1)')
    parser.add_argument('--jsonl', type=str, metavar='PATH',
                       help='Use specific JSONL file instead of auto-detecting')
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


def parse_line_for_task_event(line_data):
    """Extract task event from a parsed JSON line"""
    uuid = line_data.get('uuid')
    parent_uuid = line_data.get('parentUuid')
    is_sidechain = line_data.get('isSidechain', False)
    timestamp = line_data.get('timestamp')
    message_type = line_data.get('type')
    
    # Get usage data from message
    message = line_data.get('message', {})
    usage = message.get('usage', {})
    
    if not uuid:
        return None
    
    return {
        'uuid': uuid,
        'parent_uuid': parent_uuid,
        'is_sidechain': is_sidechain,
        'timestamp': timestamp,
        'message_type': message_type,
        'usage': usage,
        'total_tokens': calculate_total_tokens(usage) if usage else 0,
        'content_preview': get_content_preview(message)
    }


def get_content_preview(message):
    """Get a preview of message content for task identification"""
    content = message.get('content', '')
    
    # Handle string content
    if isinstance(content, str):
        return content[:100] + '...' if len(content) > 100 else content
    
    # Handle list content (tool uses, etc.)
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
                elif item.get('type') == 'tool_use':
                    tool_name = item.get('name', 'unknown_tool')
                    text_parts.append(f'[{tool_name}]')
        
        preview = ' '.join(text_parts)
        return preview[:100] + '...' if len(preview) > 100 else preview
    
    return str(content)[:100]


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
        with open(stream_file, 'r', encoding='utf-8', errors='replace') as f:
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
                except json.JSONDecodeError as e:
                    # Log the problematic line for debugging
                    print(f"[tokens] JSON decode error at line {line_num}: {e}")
                    print(f"[tokens] Problematic line preview: {line[:100]}...")
                    continue
                except Exception as e:
                    # Skip any other parsing errors
                    print(f"[tokens] Unexpected error at line {line_num}: {type(e).__name__}: {e}")
                    continue
    except (FileNotFoundError, IOError) as e:
        # File access errors - return empty list
        print(f"[tokens] File access error: {e}")
        pass
    except Exception as e:
        # Any other unexpected errors
        print(f"[tokens] Warning: Error parsing {stream_file}: {e}")
    
    return sorted(todo_events, key=lambda x: x['timestamp'])


def parse_session_tasks(stream_file):
    """Parse all task events from a single session file"""
    task_events = []
    
    try:
        with open(stream_file, 'r', encoding='utf-8', errors='replace') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    timestamp = data.get('timestamp')
                    if not timestamp:
                        continue
                    
                    task_event = parse_line_for_task_event(data)
                    if task_event:
                        task_events.append({
                            'timestamp': timestamp,
                            'line': line_num,
                            'uuid': task_event['uuid'],
                            'parent_uuid': task_event['parent_uuid'],
                            'is_sidechain': task_event['is_sidechain'],
                            'message_type': task_event['message_type'],
                            'total_tokens': task_event['total_tokens'],
                            'usage': task_event['usage'],
                            'content_preview': task_event['content_preview']
                        })
                except json.JSONDecodeError as e:
                    # Log the problematic line for debugging
                    print(f"[tokens] JSON decode error at line {line_num}: {e}")
                    print(f"[tokens] Problematic line preview: {line[:100]}...")
                    continue
                except Exception as e:
                    # Skip any other parsing errors
                    print(f"[tokens] Unexpected error at line {line_num}: {type(e).__name__}: {e}")
                    continue
    except (FileNotFoundError, IOError) as e:
        # File access errors - return empty list
        print(f"[tokens] File access error: {e}")
        pass
    except Exception as e:
        # Any other unexpected errors
        print(f"[tokens] Warning: Error parsing {stream_file}: {e}")
    
    return sorted(task_events, key=lambda x: x['timestamp'])


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
                'duration': None
                # Removed all_events to avoid serialization issues
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


def build_task_chains(task_events):
    """Build task chains from task events with correct token calculation"""
    # Group by chain: sidechain tasks and their descendants
    task_chains = {}
    all_tasks = {}
    
    # First pass: index all tasks by UUID
    for event in task_events:
        uuid = event['uuid']
        all_tasks[uuid] = event
    
    # Second pass: identify sidechain roots and build chains
    for event in task_events:
        if event['is_sidechain'] and event['parent_uuid'] is None:
            # This is a sidechain root - start a new chain
            chain_id = event['uuid']
            task_chains[chain_id] = {
                'root_task': event,
                'tasks': [],
                'total_tokens': 0,
                'task_count': 0,
                'start_time': None,
                'end_time': None
            }
            
            # Collect all tasks in this chain
            chain_tasks = collect_chain_tasks(chain_id, all_tasks)
            task_chains[chain_id]['tasks'] = chain_tasks
            
            # Calculate metrics with CORRECTED token calculation
            if chain_tasks:
                # CRITICAL FIX: Calculate token delta between start and end of chain
                sorted_tasks = sorted(chain_tasks, key=lambda x: x['timestamp'])
                
                # Find the cumulative token total at chain start and end
                start_cumulative = None
                end_cumulative = None
                
                # Get the first task with token data as the baseline
                for task in sorted_tasks:
                    if task['total_tokens'] > 0:
                        if start_cumulative is None:
                            start_cumulative = task['total_tokens']
                        # Always update end_cumulative to get the final value
                        end_cumulative = task['total_tokens']
                
                # Calculate actual token consumption for this task chain
                if start_cumulative is not None and end_cumulative is not None:
                    # Token usage = final_cumulative - initial_cumulative
                    task_chains[chain_id]['total_tokens'] = max(0, end_cumulative - start_cumulative)
                else:
                    task_chains[chain_id]['total_tokens'] = 0
                
                task_chains[chain_id]['task_count'] = len(chain_tasks)
                
                timestamps = [datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')) 
                             for t in chain_tasks if t['timestamp']]
                if timestamps:
                    task_chains[chain_id]['start_time'] = min(timestamps)
                    task_chains[chain_id]['end_time'] = max(timestamps)
    
    return task_chains


def collect_chain_tasks(chain_root_uuid, all_tasks):
    """Recursively collect all tasks in a chain"""
    chain_tasks = []
    
    def collect_descendants(parent_uuid):
        for uuid, task in all_tasks.items():
            if task['parent_uuid'] == parent_uuid:
                chain_tasks.append(task)
                # Recursively collect children
                collect_descendants(uuid)
    
    # Start from the chain root
    if chain_root_uuid in all_tasks:
        chain_tasks.append(all_tasks[chain_root_uuid])
        collect_descendants(chain_root_uuid)
    
    return sorted(chain_tasks, key=lambda x: x['timestamp'])


def analyze_sessions_tasks(stream_files):
    """Analyze task token usage grouped by session"""
    sessions_analysis = {}
    
    for stream_file in stream_files:
        session_id = stream_file.stem
        task_events = parse_session_tasks(stream_file)
        
        if task_events:
            task_chains = build_task_chains(task_events)
            
            sessions_analysis[session_id] = {
                'file': str(stream_file),
                'task_chains': task_chains,
                'event_count': len(task_events)
            }
    
    return sessions_analysis


def analyze_sessions_unified(stream_files):
    """Analyze both task and todo token usage grouped by session"""
    sessions_analysis = {}
    
    for stream_file in stream_files:
        session_id = stream_file.stem
        
        # Parse both tasks and todos
        task_events = parse_session_tasks(stream_file)
        todo_events = parse_session_todos(stream_file)
        
        unified_data = {
            'file': str(stream_file),
            'task_chains': {},
            'todos': {},
            'task_event_count': len(task_events),
            'todo_event_count': len(todo_events)
        }
        
        # Process tasks if available
        if task_events:
            task_chains = build_task_chains(task_events)
            unified_data['task_chains'] = task_chains
        
        # Process todos if available
        if todo_events:
            todo_tracking = track_todo_lifecycle(todo_events)
            todo_metrics = calculate_todo_metrics(todo_tracking)
            unified_data['todos'] = todo_metrics
        
        sessions_analysis[session_id] = unified_data
    
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


def format_session_tasks(session_id, session_data):
    """Format task output for a single session"""
    output = []
    output.append(f"\n🔗 Session: {session_id}")
    output.append("=" * 60)
    
    task_chains = session_data['task_chains']
    if not task_chains:
        output.append("No task chains found in this session.")
        return output
    
    # Sort chains by start time
    sorted_chains = sorted(
        task_chains.items(),
        key=lambda x: x[1]['start_time'] or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
    )
    
    for chain_id, chain_data in sorted_chains:
        root_task = chain_data['root_task']
        
        output.append(f"🔗 Task Chain: {chain_id[:8]}...")
        output.append(f"   Root Task: {root_task['content_preview']}")
        output.append(f"   Tasks in chain: {chain_data['task_count']}")
        output.append(f"   Total tokens: {chain_data['total_tokens']:,}")
        
        if chain_data['start_time'] and chain_data['end_time']:
            duration = chain_data['end_time'] - chain_data['start_time']
            duration_str = str(duration).split('.')[0]
            output.append(f"   Duration: {duration_str}")
        
        # Show task breakdown
        output.append("   📋 Tasks:")
        for i, task in enumerate(chain_data['tasks'][:5]):  # Limit to first 5 tasks
            task_type = task['message_type']
            tokens = task['total_tokens']
            preview = task['content_preview'][:50]
            
            if task_type == 'user':
                emoji = "👤"
            elif task_type == 'assistant':
                emoji = "🤖"
            else:
                emoji = "📝"
            
            output.append(f"      {emoji} {preview} ({tokens:,} tokens)")
        
        if len(chain_data['tasks']) > 5:
            output.append(f"      ... and {len(chain_data['tasks']) - 5} more tasks")
        
        output.append("")
    
    # Session summary
    total_tokens = sum(chain['total_tokens'] for chain in task_chains.values())
    total_tasks = sum(chain['task_count'] for chain in task_chains.values())
    
    output.append("📊 Session Summary")
    output.append("-" * 20)
    output.append(f"Total task chains: {len(task_chains)}")
    output.append(f"Total tasks: {total_tasks}")
    output.append(f"Total tokens: {total_tokens:,}")
    if task_chains:
        avg_tokens = total_tokens / len(task_chains)
        output.append(f"Avg tokens per chain: {avg_tokens:,.0f}")
    
    return output


def format_todos_brief(sessions_analysis):
    """Format brief todo output by session"""
    if not sessions_analysis:
        return "No todo data found in the selected sessions."
    
    output = []
    
    # Sort sessions by file modification time (newest first)
    sorted_sessions = sorted(
        sessions_analysis.items(),
        key=lambda x: Path(x[1]['file']).stat().st_mtime,
        reverse=True
    )
    
    for session_id, session_data in sorted_sessions:
        output.append(f"# {session_id}")
        
        todos = session_data['todos']
        if not todos:
            output.append("- No todos found")
            continue
        
        # Sort todos by started_at time
        todos_with_start = [(k, v) for k, v in todos.items() if v['started_at'] is not None]
        todos_without_start = [(k, v) for k, v in todos.items() if v['started_at'] is None]
        
        sorted_todos = (
            sorted(todos_with_start, key=lambda x: x[1]['started_at']) +
            sorted(todos_without_start, key=lambda x: x[0])
        )
        
        for todo_content, metrics in sorted_todos:
            tokens_str = f"{metrics['total_tokens']:,}tkn" if metrics['total_tokens'] else "?tkn"
            
            if metrics['duration']:
                duration_str = str(metrics['duration']).split('.')[0]
                # Convert to more readable format: 00h15m23s
                hours, remainder = divmod(metrics['duration'].total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                duration_str = f"{int(hours):02d}h{int(minutes):02d}m{int(seconds):02d}s"
            else:
                duration_str = "?duration"
            
            # Truncate content to fit brief format
            brief_content = todo_content[:50] + "..." if len(todo_content) > 50 else todo_content
            output.append(f"- {brief_content} -- {tokens_str} -- {duration_str}")
        
        output.append("")  # Blank line between sessions
    
    return "\n".join(output).rstrip()  # Remove trailing newline


def format_todos_output(sessions_analysis, json_output=False, brief=False):
    """Format the todo analytics output"""
    if not sessions_analysis:
        return "No todo data found in the selected sessions."
    
    if brief:
        return format_todos_brief(sessions_analysis)
    
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


def format_session_unified(session_id, session_data):
    """Format unified task and todo output for a single session"""
    output = []
    output.append(f"\n🔗📋 Session: {session_id}")
    output.append("=" * 60)
    
    task_chains = session_data['task_chains']
    todos = session_data['todos']
    
    if not task_chains and not todos:
        output.append("No task chains or todos found in this session.")
        return output
    
    # Show task chains first
    if task_chains:
        output.append("🔗 TASK CHAINS")
        output.append("-" * 20)
        
        # Sort chains by start time
        sorted_chains = sorted(
            task_chains.items(),
            key=lambda x: x[1]['start_time'] or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
        )
        
        for chain_id, chain_data in sorted_chains:
            root_task = chain_data['root_task']
            output.append(f"   🔗 {chain_id[:8]}... - {root_task['content_preview'][:50]}")
            output.append(f"      Tasks: {chain_data['task_count']}, Tokens: {chain_data['total_tokens']:,}")
        
        output.append("")
    
    # Show todos second
    if todos:
        output.append("📋 TODOS")
        output.append("-" * 20)
        
        # Sort todos by status and started_at
        todos_with_start = [(k, v) for k, v in todos.items() if v['started_at'] is not None]
        todos_without_start = [(k, v) for k, v in todos.items() if v['started_at'] is None]
        
        sorted_todos = (
            sorted(todos_with_start, key=lambda x: x[1]['started_at']) +
            sorted(todos_without_start, key=lambda x: x[0])
        )
        
        for todo_content, metrics in sorted_todos:
            if metrics['status'] == 'completed':
                status_emoji = "✅"
            elif metrics['status'] == 'in_progress':
                status_emoji = "⏳"
            else:
                status_emoji = "❓"
            
            tokens_info = f"{metrics['total_tokens']:,}" if metrics['total_tokens'] else "unknown"
            output.append(f"   {status_emoji} {todo_content[:60]}...")
            output.append(f"      Status: {metrics['status']}, Tokens: {tokens_info}")
        
        output.append("")
    
    # Combined summary
    task_tokens = sum(chain['total_tokens'] for chain in task_chains.values()) if task_chains else 0
    todo_tokens = sum(t['total_tokens'] for t in todos.values() if t['total_tokens']) if todos else 0
    total_tokens = task_tokens + todo_tokens
    
    output.append("📊 Session Summary")
    output.append("-" * 20)
    if task_chains:
        output.append(f"Task chains: {len(task_chains)} ({task_tokens:,} tokens)")
    if todos:
        completed_todos = len([t for t in todos.values() if t['status'] == 'completed'])
        output.append(f"Todos: {len(todos)} ({completed_todos} completed, {todo_tokens:,} tokens)")
    output.append(f"Combined total: {total_tokens:,} tokens")
    
    return output


def format_tasks_output(sessions_analysis, json_output=False):
    """Format the task analytics output"""
    if not sessions_analysis:
        return "No task data found in the selected sessions."
    
    if json_output:
        # Convert datetime objects to strings for JSON serialization
        serializable = {}
        for session_id, session_data in sessions_analysis.items():
            serializable[session_id] = {
                'file': session_data['file'],
                'event_count': session_data['event_count'],
                'task_chains': {}
            }
            for chain_id, chain_data in session_data['task_chains'].items():
                serializable[session_id]['task_chains'][chain_id] = {
                    'task_count': chain_data['task_count'],
                    'total_tokens': chain_data['total_tokens'],
                    'start_time': chain_data['start_time'].isoformat() if chain_data['start_time'] else None,
                    'end_time': chain_data['end_time'].isoformat() if chain_data['end_time'] else None,
                    'root_task_preview': chain_data['root_task']['content_preview'],
                    'tasks': [
                        {
                            'uuid': task['uuid'],
                            'message_type': task['message_type'],
                            'total_tokens': task['total_tokens'],
                            'content_preview': task['content_preview'],
                            'timestamp': task['timestamp']
                        }
                        for task in chain_data['tasks']
                    ]
                }
        return json.dumps(serializable, indent=2)
    
    # Human-readable format
    output = ["🔗 Task Chain Token Analysis"]
    
    # Sort sessions by file modification time (newest first)
    sorted_sessions = sorted(
        sessions_analysis.items(),
        key=lambda x: Path(x[1]['file']).stat().st_mtime,
        reverse=True
    )
    
    for session_id, session_data in sorted_sessions:
        output.extend(format_session_tasks(session_id, session_data))
    
    return "\n".join(output)


def format_unified_output(sessions_analysis, json_output=False):
    """Format the unified task and todo analytics output"""
    if not sessions_analysis:
        return "No task or todo data found in the selected sessions."
    
    if json_output:
        # Convert datetime objects to strings for JSON serialization
        serializable = {}
        for session_id, session_data in sessions_analysis.items():
            serializable[session_id] = {
                'file': session_data['file'],
                'task_event_count': session_data['task_event_count'],
                'todo_event_count': session_data['todo_event_count'],
                'task_chains': {},
                'todos': {}
            }
            
            # Serialize task chains
            for chain_id, chain_data in session_data['task_chains'].items():
                serializable[session_id]['task_chains'][chain_id] = {
                    'task_count': chain_data['task_count'],
                    'total_tokens': chain_data['total_tokens'],
                    'start_time': chain_data['start_time'].isoformat() if chain_data['start_time'] else None,
                    'end_time': chain_data['end_time'].isoformat() if chain_data['end_time'] else None,
                    'root_task_preview': chain_data['root_task']['content_preview']
                }
            
            # Serialize todos
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
    output = ["🔗📋 Unified Task & Todo Token Analysis"]
    
    # Sort sessions by file modification time (newest first)
    sorted_sessions = sorted(
        sessions_analysis.items(),
        key=lambda x: Path(x[1]['file']).stat().st_mtime,
        reverse=True
    )
    
    for session_id, session_data in sorted_sessions:
        output.extend(format_session_unified(session_id, session_data))
    
    return "\n".join(output)


def get_token_usage(stream_file):
    """Extract token usage from the last line of a Claude stream file"""
    try:
        with open(stream_file, 'r') as f:
            # Read the last line
            lines = f.readlines()
            if not lines:
                return None
            
            # Try to find the last message with usage info
            # Start from the end and work backwards
            for i in range(len(lines) - 1, -1, -1):
                line = lines[i].strip()
                if not line:
                    continue
                    
                try:
                    data = json.loads(line)
                    # Look for usage data in the message
                    if 'message' in data and 'usage' in data.get('message', {}):
                        usage = data['message']['usage']
                        if usage:  # Make sure it's not empty
                            return usage
                except json.JSONDecodeError:
                    continue
            
            return None
    except (FileNotFoundError, IOError) as e:
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


def format_token_stats(stats, json_output=False, brief=False):
    """Format the token usage output"""
    if not stats:
        return "No token usage data found for current conversation."
    
    if json_output:
        return json.dumps(stats, indent=2)
    
    if brief:
        # Brief format: "800 / 165,000 (0.5%)"
        return f"{stats['total_context_tokens']:,} / {stats['claude_code_cutoff']:,} ({stats['usage_percentage']:.1f}%)"
    
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
    
    if parsed.all:
        # Unified analysis mode (both tasks and todos)
        if parsed.jsonl:
            # Use specified file
            stream_files = [Path(parsed.jsonl)]
            # Verify file exists
            if not stream_files[0].exists():
                return {
                    'success': False,
                    'message': f'File not found: {parsed.jsonl}'
                }
        else:
            stream_files = get_recent_stream_files(cwd, parsed.sessions)
            if not stream_files:
                return {
                    'success': False,
                    'message': 'No Claude Code conversations found for this directory'
                }
        
        # Analyze both tasks and todos by session
        sessions_analysis = analyze_sessions_unified(stream_files)
        
        # Format output
        output = format_unified_output(sessions_analysis, parsed.json)
        
        return {
            'success': True,
            'message': output
        }
    elif parsed.tasks:
        # Task analysis mode
        if parsed.jsonl:
            # Use specified file
            stream_files = [Path(parsed.jsonl)]
            # Verify file exists
            if not stream_files[0].exists():
                return {
                    'success': False,
                    'message': f'File not found: {parsed.jsonl}'
                }
        else:
            stream_files = get_recent_stream_files(cwd, parsed.sessions)
            if not stream_files:
                return {
                    'success': False,
                    'message': 'No Claude Code conversations found for this directory'
                }
        
        # Analyze tasks by session
        sessions_analysis = analyze_sessions_tasks(stream_files)
        
        # Format output (brief not implemented for tasks yet)
        output = format_tasks_output(sessions_analysis, parsed.json)
        
        return {
            'success': True,
            'message': output
        }
    elif parsed.todos:
        # Todo analysis mode
        if parsed.jsonl:
            # Use specified file
            stream_files = [Path(parsed.jsonl)]
            # Verify file exists
            if not stream_files[0].exists():
                return {
                    'success': False,
                    'message': f'File not found: {parsed.jsonl}'
                }
        else:
            stream_files = get_recent_stream_files(cwd, parsed.sessions)
            if not stream_files:
                return {
                    'success': False,
                    'message': 'No Claude Code conversations found for this directory'
                }
        
        # Analyze todos by session
        sessions_analysis = analyze_sessions_todos(stream_files)
        
        # Format output
        output = format_todos_output(sessions_analysis, parsed.json, parsed.brief)
        
        return {
            'success': True,
            'message': output
        }
    else:
        # Regular token usage mode
        if parsed.jsonl:
            # Use specified file
            stream_file = Path(parsed.jsonl)
            if not stream_file.exists():
                return {
                    'success': False,
                    'message': f'File not found: {parsed.jsonl}'
                }
        else:
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
        output = format_token_stats(stats, parsed.json, parsed.brief)
        
        return {
            'success': True,
            'message': output
        }
