"""
List todos for a Claude session
"""
import argparse
import json
from pathlib import Path


def get_parser():
    parser = argparse.ArgumentParser(
        prog='claudecontroller todo-list',
        description='List todos for a Claude session'
    )
    parser.add_argument('--session', type=str, required=True,
                       help='Session ID to list todos from')
    parser.add_argument('--status', type=str,
                       choices=['pending', 'in_progress', 'completed'],
                       help='Filter by status')
    parser.add_argument('--priority', type=str,
                       choices=['low', 'medium', 'high'],
                       help='Filter by priority')
    parser.add_argument('--json', action='store_true',
                       help='Output in JSON format')
    return parser


def load_todos(todo_file):
    """Load todos from file"""
    if not todo_file.exists():
        return []
    
    try:
        with open(todo_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def format_todo_list(todos, filters):
    """Format todos for display"""
    # Apply filters
    filtered_todos = todos
    if filters.get('status'):
        filtered_todos = [t for t in filtered_todos if t.get('status') == filters['status']]
    if filters.get('priority'):
        filtered_todos = [t for t in filtered_todos if t.get('priority') == filters['priority']]
    
    if not filtered_todos:
        return "No todos found matching filters."
    
    # Group by status
    by_status = {
        'pending': [],
        'in_progress': [],
        'completed': []
    }
    
    for todo in filtered_todos:
        status = todo.get('status', 'pending')
        by_status[status].append(todo)
    
    # Format output
    output = []
    
    # Status emojis
    status_emoji = {
        'pending': '⏳',
        'in_progress': '🔄',
        'completed': '✅'
    }
    
    # Priority emojis
    priority_emoji = {
        'low': '🔵',
        'medium': '🟡',
        'high': '🔴'
    }
    
    for status in ['in_progress', 'pending', 'completed']:
        if by_status[status]:
            output.append(f"\n{status_emoji[status]} {status.upper().replace('_', ' ')}")
            output.append("-" * 40)
            
            for todo in by_status[status]:
                priority = todo.get('priority', 'medium')
                content = todo.get('content', 'No content')
                todo_id = todo.get('id', 'No ID')
                
                output.append(f"{priority_emoji[priority]} [{todo_id}] {content}")
    
    # Summary
    output.append(f"\n📊 Total: {len(filtered_todos)} todos")
    if len(filtered_todos) != len(todos):
        output.append(f"   (Filtered from {len(todos)} total)")
    
    return "\n".join(output)


def command(manager, args):
    parser = get_parser()
    parsed = parser.parse_args(args)
    
    # Build todo file path
    todo_file = Path.home() / '.claude' / 'todos' / f"{parsed.session}.json"
    
    # Load todos
    todos = load_todos(todo_file)
    
    if not todos:
        return {
            'success': True,
            'message': f"No todos found for session {parsed.session}"
        }
    
    # Apply filters
    filters = {
        'status': parsed.status,
        'priority': parsed.priority
    }
    
    if parsed.json:
        # JSON output
        filtered_todos = todos
        if filters['status']:
            filtered_todos = [t for t in filtered_todos if t.get('status') == filters['status']]
        if filters['priority']:
            filtered_todos = [t for t in filtered_todos if t.get('priority') == filters['priority']]
        
        return {
            'success': True,
            'message': json.dumps(filtered_todos, indent=2)
        }
    else:
        # Human-readable output
        return {
            'success': True,
            'message': format_todo_list(todos, filters)
        }