"""
Fix Claude Code's annoying "continue from where we left off" message

Usage: claudecontroller claude-amnesia-fix [--message <custom_message>] [--restore]

Examples:
  claudecontroller claude-amnesia-fix
  claudecontroller claude-amnesia-fix --message "Hello! How can I help you today?"
  claudecontroller claude-amnesia-fix --message ""  # Remove the message entirely
"""
import argparse
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


def get_parser():
    """Get argument parser for this command"""
    parser = argparse.ArgumentParser(
        prog='claudecontroller claude-amnesia-fix',
        description='Fix Claude Code\'s annoying "continue from where we left off" message'
    )
    parser.add_argument('--message', '-m', type=str, 
                       help='Custom message to replace the default (use empty string to remove)')
    parser.add_argument('--show', action='store_true',
                       help='Just show current message without modifying')
    return parser


def find_claude_cli() -> Optional[Path]:
    """Find the Claude Code CLI.js file"""
    # First try 'which claude' to find the executable
    try:
        result = subprocess.run(['which', 'claude'], capture_output=True, text=True, check=True)
        claude_path = result.stdout.strip()
        
        if claude_path:
            # Follow symlinks to get the real path
            real_path = Path(claude_path).resolve()
            
            # The cli.js is typically in the same directory or nearby
            # Check common patterns
            possible_paths = [
                real_path.parent / 'cli.js',
                real_path.parent.parent / 'cli.js',
                real_path.parent / 'lib' / 'cli.js',
                real_path.parent.parent / 'lib' / 'cli.js',
            ]
            
            for path in possible_paths:
                if path.exists() and path.is_file():
                    return path
            
            # If not found, try to find it relative to node_modules
            # Look for @anthropic-ai/claude-code pattern
            current = real_path.parent
            while current != current.parent:
                claude_code_dir = current / 'node_modules' / '@anthropic-ai' / 'claude-code'
                if claude_code_dir.exists():
                    cli_path = claude_code_dir / 'cli.js'
                    if cli_path.exists():
                        return cli_path
                current = current.parent
    except subprocess.CalledProcessError:
        pass
    
    # Fallback: search common node installation directories
    search_dirs = [
        Path.home() / '.nvm',
        Path('/usr/local/lib/node_modules'),
        Path('/usr/lib/node_modules'),
        Path.home() / '.local' / 'lib' / 'node_modules',
    ]
    
    for search_dir in search_dirs:
        if search_dir.exists():
            # Use find command for efficiency
            try:
                result = subprocess.run(
                    ['find', str(search_dir), '-path', '*/claude-code/cli.js', '-type', 'f'],
                    capture_output=True, text=True, check=True
                )
                if result.stdout.strip():
                    return Path(result.stdout.strip().split('\n')[0])
            except subprocess.CalledProcessError:
                pass
    
    return None


def extract_current_message(cli_path: Path) -> Optional[str]:
    """Extract the current continuation message from cli.js"""
    try:
        content = cli_path.read_text(encoding='utf-8')
        
        # Look for the pattern: "Please continue the conversation from where we left it off..."
        # In minified code it might be part of a larger string
        pattern = r'Please continue the conversation from where we left it off[^"\'`]*'
        match = re.search(pattern, content)
        
        if match:
            return match.group(0)
        
        return None
    except Exception as e:
        return f"Error reading file: {e}"


def replace_message(cli_path: Path, new_message: str) -> bool:
    """Replace the continuation message in cli.js"""
    try:
        content = cli_path.read_text(encoding='utf-8')
        
        # Pattern to match the full message
        pattern = r'Please continue the conversation from where we left it off without asking the user any further questions\. Continue with the last task that you were asked to work on\.'
        
        # Replace with new message
        new_content = re.sub(pattern, new_message, content)
        
        if new_content == content:
            # Try a more flexible pattern if exact match fails
            pattern = r'Please continue the conversation from where we left it off[^"\'`]*?(?=["\'`;])'
            new_content = re.sub(pattern, new_message, content)
        
        if new_content != content:
            cli_path.write_text(new_content, encoding='utf-8')
            return True
        
        return False
    except Exception:
        return False


def command(manager, args: list) -> Dict[str, Any]:
    """Execute the claude-amnesia-fix command"""
    parser = get_parser()
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        return {'success': False, 'error': 'Invalid arguments. Use "claudecontroller help claude-amnesia-fix" for usage.'}
    
    # Find the CLI.js file
    cli_path = find_claude_cli()
    
    if not cli_path:
        return {
            'success': False,
            'error': 'Could not find Claude Code CLI.js file. Is Claude Code installed?'
        }
    
    # If just showing current message
    if parsed_args.show:
        current_msg = extract_current_message(cli_path)
        if current_msg:
            return {
                'success': True,
                'message': f'Found CLI at: {cli_path}\nCurrent message: "{current_msg}"'
            }
        else:
            return {
                'success': False,
                'error': f'Could not find the continuation message in {cli_path}'
            }
    
    # If modifying the message
    if parsed_args.message is not None:
        if replace_message(cli_path, parsed_args.message):
            if parsed_args.message == "":
                result_msg = f"Successfully removed the continuation message from {cli_path}"
            else:
                result_msg = f"Successfully replaced the message in {cli_path} with:\n\"{parsed_args.message}\""
            
            return {
                'success': True,
                'message': result_msg
            }
        else:
            return {
                'success': False,
                'error': f'Failed to modify {cli_path}. The message pattern might have changed.'
            }
    
    # Default: remove the message entirely
    if replace_message(cli_path, ""):
        return {
            'success': True,
            'message': f'Successfully removed the continuation message from {cli_path}'
        }
    else:
        return {
            'success': False,
            'error': f'Failed to modify {cli_path}. The message pattern might have changed.'
        }