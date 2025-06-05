"""
Show token usage for the current Claude Code conversation
"""
import argparse
import json
import os
import re
from pathlib import Path


def get_parser():
    parser = argparse.ArgumentParser(
        prog='claudecontroller tokens',
        description='Show token usage for the current Claude Code conversation'
    )
    parser.add_argument('--json', action='store_true',
                       help='Output in JSON format')
    return parser


def sanitize_path_for_claude(path):
    """Convert a filesystem path to Claude's project directory format"""
    # Replace all non-alphanumeric characters with dashes
    sanitized = re.sub(r'[^a-zA-Z0-9]', '-', path)
    # Collapse multiple consecutive dashes (Claude seems to do some collapsing)
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized


def find_latest_stream_file(cwd):
    """Find the most recently modified .jsonl file for the current directory"""
    # Convert current working directory to Claude's format
    dir_component = sanitize_path_for_claude(cwd)
    
    # Build the Claude projects directory path
    claude_dir = Path.home() / '.claude' / 'projects' / dir_component
    
    if not claude_dir.exists():
        return None
    
    # Find all .jsonl files and get the most recent
    jsonl_files = list(claude_dir.glob('*.jsonl'))
    if not jsonl_files:
        return None
    
    # Return the most recently modified file
    return max(jsonl_files, key=lambda f: f.stat().st_mtime)


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
    claude_code_cutoff = 190000
    
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


def format_output(stats, json_output=False):
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
    
    # Find the latest stream file
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
    output = format_output(stats, parsed.json)
    
    return {
        'success': True,
        'message': output
    }