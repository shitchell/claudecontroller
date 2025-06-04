"""
Execute Claude AI as a managed process with streaming output

Usage: claudecontroller runner '<prompt>' [--context-file <file>] [--name <name>]

Examples:
  claudecontroller runner 'Explain quantum computing'
  claudecontroller runner 'Review this code' --context-file main.py
  claudecontroller runner 'Write tests' --context-file src/app.js --name code-review
"""
import subprocess
import argparse
import json
import threading
import queue
import os
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import time
import pty
import select
import fcntl
import shutil

def detect_node_setup(config: Dict[str, Any]) -> Dict[str, Any]:
    """Detect Node.js and Claude setup"""
    setup_type = config.get('type', 'auto')
    
    # If explicit paths are configured, use them
    if setup_type != 'auto':
        return {
            'type': setup_type,
            'nvm_dir': config.get('nvm_dir'),
            'nvm_script': config.get('nvm_script'),
            'node_path': config.get('node_path'),
            'claude_path': config.get('claude_path')
        }
    
    # Auto-detect setup
    info = {
        'type': 'unknown',
        'nvm_dir': None,
        'nvm_script': None,
        'node_path': None,
        'claude_path': None
    }
    
    # Check for claude in PATH first
    claude_in_path = shutil.which('claude')
    if claude_in_path:
        info['claude_path'] = claude_in_path
        info['type'] = 'system'
        return info
    
    # Check for NVM
    nvm_dir = os.environ.get('NVM_DIR', os.path.expanduser('~/.nvm'))
    if os.path.exists(nvm_dir):
        nvm_script = os.path.join(nvm_dir, 'nvm.sh')
        if os.path.exists(nvm_script):
            info['type'] = 'nvm'
            info['nvm_dir'] = nvm_dir
            info['nvm_script'] = nvm_script
            
            # Try to find claude via nvm
            try:
                result = subprocess.run(
                    f'source {nvm_script} && which claude',
                    shell=True, capture_output=True, text=True,
                    executable='/bin/bash'
                )
                if result.returncode == 0 and result.stdout.strip():
                    info['claude_path'] = result.stdout.strip()
            except:
                pass
            return info
    
    # Check for other node version managers
    # Check asdf
    asdf_dir = os.path.expanduser('~/.asdf')
    if os.path.exists(asdf_dir):
        asdf_script = os.path.join(asdf_dir, 'asdf.sh')
        if os.path.exists(asdf_script):
            info['type'] = 'asdf'
            info['nvm_script'] = asdf_script  # Reuse nvm_script field
            return info
    
    # Check for fnm
    if shutil.which('fnm'):
        info['type'] = 'fnm'
        return info
    
    # Check for volta
    volta_home = os.environ.get('VOLTA_HOME', os.path.expanduser('~/.volta'))
    if os.path.exists(volta_home):
        info['type'] = 'volta'
        return info
    
    # Check for n
    if shutil.which('n'):
        info['type'] = 'n'
        return info
    
    # Check for system node
    node_path = shutil.which('node')
    if node_path:
        info['type'] = 'system'
        info['node_path'] = node_path
        
        # Try to find claude in node's bin directory
        node_bin = os.path.dirname(node_path)
        possible_claude = os.path.join(node_bin, 'claude')
        if os.path.exists(possible_claude):
            info['claude_path'] = possible_claude
    
    return info

def get_parser():
    """Get argument parser for this command"""
    parser = argparse.ArgumentParser(
        prog='claudecontroller runner',
        description='Execute Claude AI as a managed process'
    )
    parser.add_argument('prompt', help='The prompt to send to Claude')
    parser.add_argument('--context-file', '-c', help='File to prepend to the prompt')
    parser.add_argument('--report', '-r', help='Request Claude to write a report to this file')
    parser.add_argument('--name', '-n', help='Process name (auto-generated if not specified)')
    parser.add_argument('--model', '-m', help='Claude model to use')
    parser.add_argument('--no-permissions', action='store_true', 
                       help='Disable --dangerously-skip-permissions flag')
    return parser

def parse_stream_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a line from the Claude JSON stream"""
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None

def stderr_reader(proc: subprocess.Popen, error_log, report_data):
    """Read stderr output"""
    stderr_lines = []
    try:
        for line in proc.stderr:
            error_log.write(f"[STDERR] {line}")
            error_log.flush()
            stderr_lines.append(line.strip())
    except Exception as e:
        error_log.write(f"[STDERR ERROR] {str(e)}\n")
    
    # Store stderr in report data
    if stderr_lines:
        report_data['stderr'] = '\n'.join(stderr_lines)

def stream_parser(proc: subprocess.Popen, stream_log, report_data: Dict[str, Any], 
                 process_name: str, manager):
    """Parse the streaming output from Claude"""
    tool_counts = {}
    start_time = time.time()
    session_id = None
    model = None
    total_input_tokens = 0
    total_output_tokens = 0
    
    try:
        stream_log.write("[DEBUG] Stream parser started\n")
        stream_log.flush()
        
        for line in proc.stdout:
            # Write to stream log
            stream_log.write(line)
            stream_log.flush()
            
            # Parse JSON
            data = parse_stream_line(line)
            if not data:
                continue
            
            # Get session ID
            if 'session_id' in data and not session_id:
                session_id = data['session_id']
                report_data['session_id'] = session_id
            
            # Track system init
            if data.get('type') == 'system' and data.get('subtype') == 'init':
                report_data['tools_available'] = data.get('tools', [])
            
            # Track tool usage and tokens
            elif data.get('type') == 'assistant':
                message = data.get('message', {})
                
                # Get model info
                if not model and 'model' in message:
                    model = message['model']
                    report_data['model'] = model
                
                # Track tool usage
                content = message.get('content', [])
                for item in content:
                    if item.get('type') == 'tool_use':
                        tool_name = item.get('name', 'unknown')
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                
                # Update token usage
                usage = message.get('usage', {})
                if usage:
                    total_input_tokens += usage.get('input_tokens', 0)
                    total_input_tokens += usage.get('cache_creation_input_tokens', 0)
                    total_input_tokens += usage.get('cache_read_input_tokens', 0)
                    total_output_tokens += usage.get('output_tokens', 0)
            
            # Check for final result
            elif data.get('type') == 'result':
                report_data['status'] = data.get('subtype', 'unknown')
                report_data['result'] = data.get('result', '')
                report_data['cost_usd'] = data.get('cost_usd', 0)
                report_data['total_cost'] = data.get('total_cost', 0)
                report_data['duration_ms'] = data.get('duration_ms', 0)
                report_data['duration_api_ms'] = data.get('duration_api_ms', 0)
                report_data['num_turns'] = data.get('num_turns', 0)
                report_data['is_error'] = data.get('is_error', False)
    
    except Exception as e:
        report_data['error'] = str(e)
        report_data['status'] = 'error'
        report_data['is_error'] = True
    
    finally:
        # Update final metrics
        report_data['tool_counts'] = tool_counts
        report_data['duration'] = time.time() - start_time
        report_data['total_input_tokens'] = total_input_tokens
        report_data['total_output_tokens'] = total_output_tokens
        report_data['total_tokens'] = total_input_tokens + total_output_tokens
        
        # Update process info in manager
        if process_name in manager.process_info:
            manager.process_info[process_name].update({
                'tool_counts': tool_counts,
                'total_tokens': total_input_tokens + total_output_tokens,
                'total_input_tokens': total_input_tokens,
                'total_output_tokens': total_output_tokens,
                'status': report_data.get('status', 'unknown'),
                'cost_usd': report_data.get('cost_usd', 0),
                'model': model,
                'is_error': report_data.get('is_error', False)
            })

def command(manager, args: list) -> Dict[str, Any]:
    """Execute Claude as a managed process"""
    # Parse arguments
    parser = get_parser()
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        return {'success': False, 'error': 'Invalid arguments. Use "claudecontroller help runner" for usage.'}
    
    # Build the prompt
    prompt = parsed_args.prompt
    if parsed_args.context_file:
        try:
            context_path = Path(parsed_args.context_file)
            if not context_path.exists():
                return {'success': False, 'error': f'Context file not found: {parsed_args.context_file}'}
            
            with open(context_path, 'r') as f:
                context = f.read()
            prompt = f"@{parsed_args.context_file}\n{prompt}"
        except Exception as e:
            return {'success': False, 'error': f'Error reading context file: {str(e)}'}
    
    # Add report request if specified
    if parsed_args.report:
        prompt = f"{prompt}\n\nPlease write a full report to {parsed_args.report}"
    
    # Load configuration
    config = manager.config.get('claude_runner', {})
    use_dangerous_perms = config.get('dangerously_skip_permissions', True)
    node_setup = config.get('node_setup', {})
    
    # Detect Node/Claude setup
    setup_info = detect_node_setup(node_setup)
    
    # Build Claude command
    claude_cmd_parts = ['claude', '-p', prompt, '--verbose', '--output-format', 'stream-json']
    
    if parsed_args.model:
        claude_cmd_parts.extend(['--model', parsed_args.model])
    
    if use_dangerous_perms and not parsed_args.no_permissions:
        claude_cmd_parts.append('--dangerously-skip-permissions')
    
    # Escape the prompt for shell using shlex
    import shlex
    escaped_prompt = shlex.quote(prompt)
    
    # Build command with proper escaping
    claude_args = ['--verbose', '--output-format', 'stream-json']
    if parsed_args.model:
        claude_args.extend(['--model', parsed_args.model])
    if use_dangerous_perms and not parsed_args.no_permissions:
        claude_args.append('--dangerously-skip-permissions')
    
    # Setup environment variables for wrapper
    env_vars = {
        'CLAUDECONTROLLER_NODE_TYPE': setup_info.get('type', 'unknown'),
    }
    
    if setup_info.get('nvm_dir'):
        env_vars['CLAUDECONTROLLER_NVM_DIR'] = setup_info['nvm_dir']
    if setup_info.get('nvm_script'):
        env_vars['CLAUDECONTROLLER_NVM_SCRIPT'] = setup_info['nvm_script']
    if setup_info.get('node_path'):
        env_vars['CLAUDECONTROLLER_NODE_PATH'] = setup_info['node_path']
    if setup_info.get('claude_path'):
        env_vars['CLAUDECONTROLLER_CLAUDE_PATH'] = setup_info['claude_path']
    
    # Use the claude wrapper script
    wrapper_path = Path(__file__).parent.parent / 'scripts' / 'claude-wrapper.sh'
    claude_cmd = f"{wrapper_path} -p {escaped_prompt} {' '.join(claude_args)}"
    full_command = claude_cmd  # Run directly without bash -c
    
    # Set up logging
    log_dir = Path(__file__).parent.parent / 'logs' / 'claude'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        # Start the process
        # Set unbuffered output and add our env vars
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['TERM'] = 'xterm-256color'
        env.update(env_vars)  # Add our setup variables
        
        proc = subprocess.Popen(
            full_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=0,  # Unbuffered
            env=env
        )
        
        # Generate process name
        if not parsed_args.name:
            parsed_args.name = f"claude-{proc.pid}"
        process_name = f"{parsed_args.name}-{proc.pid}"
        
        # Create log files
        stream_log_path = log_dir / f"{timestamp}_{process_name}_stream.jsonl"
        report_log_path = log_dir / f"{timestamp}_{process_name}_report.json"
        
        # Initialize report data
        report_data = {
            'process_name': process_name,
            'pid': proc.pid,
            'started': datetime.now().isoformat(),
            'prompt': parsed_args.prompt,
            'context_file': parsed_args.context_file,
            'report_file': parsed_args.report,
            'model': parsed_args.model,
            'command': full_command,
            'node_setup': setup_info  # Store setup info
        }
        
        # Open log file and keep it open
        stream_log = open(stream_log_path, 'w')
        
        # Write initial debug info
        stream_log.write(f"[DEBUG] Command: {full_command}\n")
        stream_log.write(f"[DEBUG] Started at: {datetime.now().isoformat()}\n")
        stream_log.flush()
        
        # Start stream parser in background
        parser_thread = threading.Thread(
            target=stream_parser,
            args=(proc, stream_log, report_data, process_name, manager)
        )
        parser_thread.daemon = True
        parser_thread.start()
        
        # Also capture stderr
        stderr_thread = threading.Thread(
            target=stderr_reader,
            args=(proc, stream_log, report_data)
        )
        stderr_thread.daemon = True
        stderr_thread.start()
        
        # Store process info
        manager.processes[process_name] = proc
        manager.process_info[process_name] = {
            'command': full_command,
            'started': datetime.now().isoformat(),
            'type': 'claude',
            'pid': proc.pid,
            'prompt': parsed_args.prompt,
            'context_file': parsed_args.context_file,
            'model': parsed_args.model,
            'stream_log': str(stream_log_path),
            'report_log': str(report_log_path),
            'report_data': report_data
        }
        
        # Monitor process and write report when done
        def monitor_process():
            proc.wait()
            report_data['ended'] = datetime.now().isoformat()
            report_data['return_code'] = proc.returncode
            
            # Wait for parser threads to finish
            parser_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            
            # Close log file
            stream_log.close()
            
            # Write final report
            with open(report_log_path, 'w') as f:
                json.dump(report_data, f, indent=2)
        
        monitor_thread = threading.Thread(target=monitor_process)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return {
            'success': True,
            'pid': proc.pid,
            'name': process_name,
            'message': f'Started Claude runner "{process_name}" with PID {proc.pid}\n' +
                      f'Stream log: {stream_log_path.name}\n' +
                      f'Report log: {report_log_path.name}'
        }
        
    except Exception as e:
        return {'success': False, 'error': f'Failed to start Claude runner: {str(e)}'}