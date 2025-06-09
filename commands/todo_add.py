"""
Add a todo item to a Claude session's todo list
"""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime
import uuid


def get_parser():
    parser = argparse.ArgumentParser(
        prog='claudecontroller todo-add',
        description='Add a todo item to a Claude session'
    )
    parser.add_argument('content', type=str,
                       help='The todo item content')
    parser.add_argument('--session', type=str, required=True,
                       help='Session ID to add the todo to')
    parser.add_argument('--status', type=str, default='pending',
                       choices=['pending', 'in_progress', 'completed'],
                       help='Initial status of the todo (default: pending)')
    parser.add_argument('--priority', type=str, default='medium',
                       choices=['low', 'medium', 'high'],
                       help='Priority of the todo (default: medium)')
    parser.add_argument('--id', type=str,
                       help='Custom ID for the todo (default: auto-generated)')
    return parser


def load_todos(todo_file):
    """Load todos from file, return empty list if doesn't exist"""
    if todo_file.exists():
        try:
            with open(todo_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_todos(todo_file, todos):
    """Save todos to file"""
    # Ensure the directory exists
    todo_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(todo_file, 'w') as f:
        json.dump(todos, f, indent=2)


def generate_todo_id():
    """Generate a unique todo ID"""
    # Use timestamp + short UUID for uniqueness and readability
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    short_uuid = str(uuid.uuid4())[:8]
    return f"todo_{timestamp}_{short_uuid}"


def command(manager, args):
    parser = get_parser()
    parsed = parser.parse_args(args)
    
    # Build todo file path
    todo_dir = Path.home() / '.claude' / 'todos'
    todo_file = todo_dir / f"{parsed.session}.json"
    
    # Load existing todos
    todos = load_todos(todo_file)
    
    # Create new todo
    new_todo = {
        'content': parsed.content,
        'status': parsed.status,
        'priority': parsed.priority,
        'id': parsed.id or generate_todo_id()
    }
    
    # Check for duplicate IDs
    if any(todo['id'] == new_todo['id'] for todo in todos):
        return {
            'success': False,
            'error': f"Todo with ID '{new_todo['id']}' already exists"
        }
    
    # Add to list
    todos.append(new_todo)
    
    # Save
    try:
        save_todos(todo_file, todos)
        
        return {
            'success': True,
            'message': f"Added todo '{new_todo['content']}' (ID: {new_todo['id']}) to session {parsed.session}\nTotal todos: {len(todos)}"
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to save todo: {str(e)}"
        }