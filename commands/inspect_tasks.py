"""
Inspect Task agent actions from Claude JSONL files
"""
import argparse
import json
import os
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects and other non-serializable types"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Path):
            return str(obj)
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            # Let the base class raise the TypeError
            return super().default(obj)


def get_parser():
    parser = argparse.ArgumentParser(
        prog='claudecontroller inspect-tasks',
        description='Inspect Task agent actions from Claude JSONL files'
    )
    parser.add_argument('regex', type=str, nargs='?', default='.*',
                       help='Regular expression pattern to search for in task descriptions (default: all tasks)')
    parser.add_argument('--project', type=str, metavar='DIR',
                       help='Absolute path to project directory (default: current directory)')
    parser.add_argument('--session', type=str, metavar='ID',
                       help='Specific session ID to analyze')
    parser.add_argument('--json', action='store_true',
                       help='Output in JSON format')
    return parser


def sanitize_path_for_claude(path):
    """Convert a filesystem path to Claude's project directory format"""
    # Replace all non-alphanumeric characters with dashes
    sanitized = re.sub(r'[^a-zA-Z0-9]', '-', path)
    # Collapse multiple consecutive dashes
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized


def get_claude_project_dir(project_path):
    """Get the Claude project directory for the given path"""
    dir_component = sanitize_path_for_claude(project_path)
    return Path.home() / '.claude' / 'projects' / dir_component


def find_session_files(project_path, session_id=None):
    """Find JSONL files for the project and optional session"""
    claude_dir = get_claude_project_dir(project_path)
    
    if not claude_dir.exists():
        return []
    
    if session_id:
        # Look for specific session
        session_file = claude_dir / f"{session_id}.jsonl"
        return [session_file] if session_file.exists() else []
    
    # Return all JSONL files
    return list(claude_dir.glob('*.jsonl'))


def collapse_whitespace(text):
    """Replace all whitespace sequences with single spaces"""
    if not text:
        return text
    # Replace all whitespace (including newlines, tabs, etc.) with single space
    return ' '.join(str(text).split())


def summarize_tool_use(tool_name, tool_input):
    """Create a concise summary of a tool use"""
    if tool_name == "Bash":
        cmd = collapse_whitespace(tool_input.get('command', ''))
        desc = collapse_whitespace(tool_input.get('description', ''))
        # Truncate long commands
        if len(cmd) > 110:
            cmd = cmd[:107] + "..."
        return f"$ {cmd}" + (f" # {desc}" if desc else "")
    
    elif tool_name == "Read":
        path = collapse_whitespace(tool_input.get('file_path', ''))
        limit = tool_input.get('limit')
        offset = tool_input.get('offset')
        summary = f"Read: {path}"
        if offset:
            summary += f" (lines {offset}-{offset + (limit or 2000)})"
        elif limit:
            summary += f" (first {limit} lines)"
        return summary
    
    elif tool_name == "Write":
        path = collapse_whitespace(tool_input.get('file_path', ''))
        content = tool_input.get('content', '')
        lines = content.count('\n') + 1 if content else 0
        chars = len(content)
        return f"Write: {path} ({lines} lines, {chars} chars)"
    
    elif tool_name == "Edit":
        path = collapse_whitespace(tool_input.get('file_path', ''))
        old = collapse_whitespace(tool_input.get('old_string', ''))[:30]
        new = collapse_whitespace(tool_input.get('new_string', ''))[:30]
        replace_all = tool_input.get('replace_all', False)
        return f"Edit: {path} - '{old}...' → '{new}...' {'(all)' if replace_all else ''}"
    
    elif tool_name == "MultiEdit":
        path = collapse_whitespace(tool_input.get('file_path', ''))
        edits = tool_input.get('edits', [])
        return f"MultiEdit: {path} ({len(edits)} edits)"
    
    elif tool_name == "Glob":
        pattern = collapse_whitespace(tool_input.get('pattern', ''))
        path = collapse_whitespace(tool_input.get('path', ''))
        return f"Glob: {pattern}" + (f" in {path}" if path else "")
    
    elif tool_name == "Grep":
        pattern = collapse_whitespace(tool_input.get('pattern', ''))[:50]
        include = collapse_whitespace(tool_input.get('include', ''))
        return f"Grep: /{pattern}/" + (f" in {include}" if include else "")
    
    elif tool_name == "LS":
        path = collapse_whitespace(tool_input.get('path', ''))
        return f"List: {path}"
    
    elif tool_name == "TodoWrite":
        todos = tool_input.get('todos', [])
        if not todos:
            return "Clear todos"
        return f"Update todos ({len(todos)} items)"
    
    elif tool_name == "TodoRead":
        return "Read todos"
    
    elif tool_name == "WebSearch":
        query = collapse_whitespace(tool_input.get('query', ''))[:50]
        return f"Search web: {query}"
    
    elif tool_name == "WebFetch":
        url = collapse_whitespace(tool_input.get('url', ''))
        return f"Fetch: {url}"
    
    elif tool_name == "Task":
        desc = collapse_whitespace(tool_input.get('description', ''))
        prompt = collapse_whitespace(tool_input.get('prompt', ''))[:50]
        return f"Task: {desc} - {prompt}..."
    
    else:
        # Generic fallback
        return f"{tool_name}: {collapse_whitespace(str(json.dumps(tool_input))[:80])}..."


def summarize_tool_result(tool_result):
    """Create a concise summary of a tool result"""
    if isinstance(tool_result, dict):
        # Handle structured results
        if 'stdout' in tool_result:
            stdout = tool_result.get('stdout', '').strip()
            stderr = tool_result.get('stderr', '').strip()
            if stderr:
                return collapse_whitespace(f"Error: {stderr[:80]}...")
            elif stdout:
                # Collapse whitespace to keep on one line
                collapsed = collapse_whitespace(stdout)
                if len(collapsed) > 230:
                    return collapsed[:227] + "..."
                return collapsed
        
        elif 'filenames' in tool_result:
            files = tool_result.get('filenames', [])
            count = tool_result.get('numFiles', len(files))
            if count == 0:
                return "No matches found"
            elif count <= 3:
                return f"Found: {', '.join(files)}"
            else:
                return f"Found {count} files: {', '.join(files[:3])}, ..."
        
        elif 'content' in tool_result:
            content = tool_result.get('content', '')
            if isinstance(content, list) and content:
                # Handle assistant responses
                text_content = [item.get('text', '') for item in content if item.get('type') == 'text']
                if text_content:
                    first_text = text_content[0][:100]
                    return first_text + "..." if len(first_text) == 100 else first_text
            return str(content)[:100] + "..."
    
    # Handle string results
    result_str = str(tool_result)
    if len(result_str) > 100:
        return result_str[:97] + "..."
    return result_str


def parse_jsonl_for_tasks(jsonl_file, pattern):
    """Parse JSONL file and find tasks matching the pattern"""
    matches = []
    pattern_re = re.compile(pattern, re.IGNORECASE)
    
    try:
        with open(jsonl_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            
        # First pass: find task descriptions matching pattern
        task_indices = []
        for i, line in enumerate(lines):
            try:
                data = json.loads(line.strip())
                # Look for Task tool uses in assistant messages
                if data.get('type') == 'assistant' and 'message' in data:
                    content = data['message'].get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if (isinstance(item, dict) and 
                                item.get('type') == 'tool_use' and 
                                item.get('name') == 'Task'):
                                # Check both description and prompt
                                desc = item.get('input', {}).get('description', '')
                                prompt = item.get('input', {}).get('prompt', '')
                                if pattern_re.search(desc) or pattern_re.search(prompt):
                                    task_indices.append((i, data, item))
            except:
                continue
        
        # Second pass: collect sidechains for each matching task
        for task_idx, task_data, task_item in task_indices:
            # Find where sidechains start (after this task)
            sidechains = []
            
            # Look forward from the task to find its sidechains
            for j in range(task_idx + 1, len(lines)):
                try:
                    data = json.loads(lines[j].strip())
                    
                    # Stop when we hit a non-sidechain entry
                    if not data.get('isSidechain', False):
                        break
                    
                    # Collect sidechain entry
                    sidechain_summary = create_sidechain_summary(data)
                    if sidechain_summary:
                        sidechains.append({
                            'raw': data,
                            'summary': sidechain_summary
                        })
                        
                except:
                    continue
            
            matches.append({
                'task': {
                    'uuid': task_data.get('uuid'),
                    'timestamp': task_data.get('timestamp'),
                    'description': task_item['input'].get('description', ''),
                    'prompt': task_item['input'].get('prompt', ''),
                    'raw': task_data
                },
                'sidechains': sidechains
            })
    
    except Exception as e:
        print(f"Error parsing {jsonl_file}: {e}")
    
    return matches


def create_sidechain_summary(data):
    """Create a summary for a sidechain entry"""
    summary = {
        'uuid': data.get('uuid'),
        'timestamp': data.get('timestamp'),
        'type': data.get('type'),
        'parent_uuid': data.get('parentUuid')
    }
    
    message = data.get('message', {})
    
    # Handle different message types
    if data['type'] == 'assistant':
        content = message.get('content', [])
        if isinstance(content, list):
            for item in content:
                if item.get('type') == 'tool_use':
                    tool_name = item.get('name')
                    tool_input = item.get('input', {})
                    summary['action'] = summarize_tool_use(tool_name, tool_input)
                    summary['tool'] = tool_name
                    break
                elif item.get('type') == 'text':
                    text = item.get('text', '')[:100]
                    summary['action'] = f"Response: {text}..."
                    break
    
    elif data['type'] == 'user':
        # Tool results
        content = message.get('content', [])
        if isinstance(content, list):
            for item in content:
                if item.get('type') == 'tool_result':
                    result = data.get('toolUseResult', {})
                    summary['action'] = f"Result: {summarize_tool_result(result)}"
                    break
    
    return summary


def format_hierarchical_output(all_matches, project_path):
    """Format matches in hierarchical text output"""
    output = []
    output.append(f"\n📁 Project: {project_path}")
    output.append("=" * 80)
    
    if not all_matches:
        output.append("No matching tasks found.")
        return "\n".join(output)
    
    # Group by session
    by_session = defaultdict(list)
    for session_file, matches in all_matches:
        session_id = Path(session_file).stem
        by_session[session_id].extend(matches)
    
    for session_id, session_matches in by_session.items():
        output.append(f"\n📂 Session: {session_id}")
        output.append("-" * 60)
        
        for i, match in enumerate(session_matches, 1):
            task = match['task']
            sidechains = match['sidechains']
            
            # Format timestamp
            timestamp = task.get('timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    timestamp_str = timestamp
            else:
                timestamp_str = 'Unknown time'
            
            output.append(f"\n  🎯 Task {i}: {task.get('description', 'No description')}")
            output.append(f"     ID: {task.get('uuid', 'Unknown')[:8]}...")
            output.append(f"     Time: {timestamp_str}")
            
            # Show prompt preview
            prompt = task.get('prompt', '')
            if prompt:
                prompt_preview = prompt[:100].replace('\n', ' ')
                if len(prompt) > 100:
                    prompt_preview += "..."
                output.append(f"     Prompt: {prompt_preview}")
            
            # Show sidechains
            if sidechains:
                output.append(f"     Actions ({len(sidechains)}):")
                
                # Track action numbers across tool calls and results
                action_num = 1
                i = 0
                while i < len(sidechains):
                    sidechain = sidechains[i]
                    summary = sidechain['summary']
                    tool_name = summary.get('tool')
                    
                    if tool_name:
                        # This is a tool call
                        action = summary.get('action', 'Unknown action')
                        # Extract just the command/content part for cleaner display
                        if action.startswith('$ '):
                            tool_display = f"{tool_name}({action[2:]})"
                        elif action.startswith('Read: '):
                            tool_display = f"{tool_name}({action[6:]})"
                        elif action.startswith('Write: '):
                            tool_display = f"{tool_name}({action[7:]})"
                        elif action.startswith('Edit: '):
                            tool_display = f"{tool_name}({action[6:]})"
                        elif action.startswith('Grep: '):
                            tool_display = f"{tool_name}({action[6:]})"
                        elif action.startswith('Glob: '):
                            tool_display = f"{tool_name}({action[6:]})"
                        elif action.startswith('List: '):
                            tool_display = f"{tool_name}({action[6:]})"
                        else:
                            tool_display = f"{tool_name}(...)"
                        
                        output.append(f"       {action_num}. {tool_display}")
                        
                        # Look for the next result
                        if i + 1 < len(sidechains):
                            next_summary = sidechains[i + 1]['summary']
                            if next_summary.get('action', '').startswith('Result: '):
                                result = next_summary['action'][8:]  # Remove "Result: " prefix
                                # Collapse all whitespace to single spaces
                                result = collapse_whitespace(result)
                                if len(result) > 130:
                                    result = result[:127] + "..."
                                output.append(f"          → {result}")
                                i += 1  # Skip the result in the next iteration
                        
                        action_num += 1
                    elif summary.get('action', '').startswith('Response: '):
                        # Assistant response
                        response = summary['action'][10:]  # Remove "Response: " prefix
                        # Format response with proper indentation
                        if len(response) > 70:
                            # Split longer responses
                            output.append(f"       {action_num}. Response:")
                            output.append(f"          {response}")
                        else:
                            output.append(f"       {action_num}. Response: {response}")
                        action_num += 1
                    
                    i += 1
            else:
                output.append("     Actions: None")
    
    # Summary
    total_tasks = sum(len(matches) for _, matches in all_matches)
    total_sidechains = sum(len(m['sidechains']) for _, matches in all_matches for m in matches)
    
    output.append(f"\n📊 Summary")
    output.append("-" * 20)
    output.append(f"Sessions analyzed: {len(by_session)}")
    output.append(f"Matching tasks: {total_tasks}")
    output.append(f"Total actions: {total_sidechains}")
    
    return "\n".join(output)


def format_json_output(all_matches):
    """Format matches as JSON output"""
    result = []
    
    for session_file, matches in all_matches:
        for match in matches:
            # Build clean JSON structure
            task_obj = {
                'uuid': match['task'].get('uuid'),
                'timestamp': match['task'].get('timestamp'),
                'description': match['task'].get('description'),
                'prompt': match['task'].get('prompt'),
                'session_id': Path(session_file).stem,
                'session_file': str(session_file)
            }
            
            # Include full sidechain data without truncation
            sidechains = []
            for sc in match['sidechains']:
                # Get the raw data for complete information
                raw_data = sc['raw']
                summary = sc['summary']
                
                sidechain_obj = {
                    'uuid': summary.get('uuid'),
                    'timestamp': summary.get('timestamp'),
                    'type': summary.get('type'),
                    'parent_uuid': summary.get('parent_uuid'),
                    'tool': summary.get('tool'),
                    'action': summary.get('action'),  # Keep summary for reference
                }
                
                # Add full content based on type
                message = raw_data.get('message', {})
                if raw_data['type'] == 'assistant':
                    content = message.get('content', [])
                    if isinstance(content, list):
                        for item in content:
                            if item.get('type') == 'tool_use':
                                sidechain_obj['tool_input'] = item.get('input', {})
                                sidechain_obj['tool_id'] = item.get('id')
                            elif item.get('type') == 'text':
                                sidechain_obj['text'] = item.get('text', '')
                elif raw_data['type'] == 'user':
                    # Tool results
                    if 'toolUseResult' in raw_data:
                        sidechain_obj['tool_result'] = raw_data['toolUseResult']
                
                sidechains.append(sidechain_obj)
            
            result.append({
                'task': task_obj,
                'sidechains': sidechains
            })
    
    return json.dumps(result, indent=2, cls=SafeJSONEncoder)


def command(manager, args):
    parser = get_parser()
    parsed = parser.parse_args(args)
    
    # Get project path
    project_path = parsed.project or os.getcwd()
    if not os.path.isabs(project_path):
        return {
            'success': False,
            'message': 'Project path must be absolute'
        }
    
    # Find session files
    session_files = find_session_files(project_path, parsed.session)
    if not session_files:
        return {
            'success': False,
            'message': f'No Claude sessions found for project: {project_path}'
        }
    
    # Parse each session file
    all_matches = []
    for session_file in session_files:
        matches = parse_jsonl_for_tasks(session_file, parsed.regex)
        if matches:
            all_matches.append((session_file, matches))
    
    # Format output
    if parsed.json:
        try:
            output = format_json_output(all_matches)
        except Exception as e:
            return {
                'success': False,
                'message': f'Error generating JSON output: {type(e).__name__}: {str(e)}'
            }
    else:
        output = format_hierarchical_output(all_matches, project_path)
    
    return {
        'success': True,
        'message': output
    }