"""
Show Claude Code stream file paths for the current directory
"""
import argparse
import os
import re
from pathlib import Path
from datetime import datetime


def get_parser():
    parser = argparse.ArgumentParser(
        prog='claudecontroller streamfile',
        description='Show Claude Code stream file paths for the current directory'
    )
    parser.add_argument('--all', action='store_true',
                       help='Show all stream files with timestamps')
    return parser


def sanitize_path_for_claude(path):
    """Convert a filesystem path to Claude's project directory format"""
    # Replace all non-alphanumeric characters with dashes
    sanitized = re.sub(r'[^a-zA-Z0-9]', '-', path)
    # Collapse multiple consecutive dashes
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized


def get_claude_project_dir(cwd):
    """Get the Claude project directory for the current working directory"""
    dir_component = sanitize_path_for_claude(cwd)
    return Path.home() / '.claude' / 'projects' / dir_component


def get_streamfiles(cwd):
    """Get all .jsonl files for the current directory"""
    claude_dir = get_claude_project_dir(cwd)
    
    if not claude_dir.exists():
        return []
    
    # Find all .jsonl files
    jsonl_files = list(claude_dir.glob('*.jsonl'))
    return jsonl_files


def format_timestamp(timestamp):
    """Format a timestamp for display"""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def command(manager, args):
    parser = get_parser()
    parsed = parser.parse_args(args)
    
    # Get current working directory
    cwd = os.getcwd()
    
    # Get all stream files
    streamfiles = get_streamfiles(cwd)
    
    if not streamfiles:
        return {
            'success': False,
            'message': 'No Claude Code stream files found for this directory'
        }
    
    if parsed.all:
        # Show all files sorted by modification time
        streamfiles.sort(key=lambda f: f.stat().st_mtime)
        
        output = []
        for f in streamfiles:
            timestamp = format_timestamp(f.stat().st_mtime)
            output.append(f"{timestamp}\t{f.absolute()}")
        
        return {
            'success': True,
            'message': '\n'.join(output)
        }
    else:
        # Show only the most recent file
        latest = max(streamfiles, key=lambda f: f.stat().st_mtime)
        
        return {
            'success': True,
            'message': str(latest.absolute())
        }