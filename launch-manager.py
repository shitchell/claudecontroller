#!/usr/bin/env python3
"""
Claude Controller Launch Manager
A flexible process manager with plugin-based command system
"""
import socket
import threading
import json
import subprocess
import os
import signal
import time
import sys
import importlib.util
import inspect
import logging
import atexit
from pathlib import Path
from typing import Dict, Any, Callable, Optional, Tuple
from datetime import datetime
import psutil

class ProcessManager:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.process_info: Dict[str, Dict[str, Any]] = {}
        self.commands: Dict[str, Callable] = {}
        self.command_help: Dict[str, str] = {}
        self.command_modules: Dict[str, Any] = {}  # Store modules for help
        
        # Load configuration
        self.controller_dir = Path(__file__).resolve().parent
        self.config = self._load_config()
        
        # Get socket path from config
        socket_filename = self.config.get('socket', {}).get('path', 'claude_controller.sock')
        self.socket_path = str(self.controller_dir / socket_filename)
        self.socket_timeout = self.config.get('socket', {}).get('timeout', 1.0)
        self.running = True
        
        # PID file management
        self.pid_file = self.controller_dir / '.pid'
        
        # Set up logging
        self._setup_logging()
        
        # Create PID file and register cleanup
        self._create_pid_file()
        
        # Load built-in commands
        self._register_builtin_commands()
        
        # Load plugin commands
        self._load_plugin_commands()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from config.json"""
        config_path = self.controller_dir / 'config.json'
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config.json: {e}")
        
        # Return default configuration
        return {
            'socket': {
                'path': 'claude_controller.sock',
                'timeout': 1.0
            },
            'logging': {
                'level': 'INFO',
                'format': '%(asctime)s [%(levelname)s] %(message)s'
            },
            'process': {
                'termination_timeout': 5
            }
        }
    
    def _setup_logging(self):
        """Set up logging for the manager"""
        log_dir = self.controller_dir / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        # Create log file with timestamp and PID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pid = os.getpid()
        log_file = log_dir / f'launch-manager_{timestamp}_{pid}.log'
        
        # Get logging config
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO').upper(), logging.INFO)
        log_format = log_config.get('format', '%(asctime)s [%(levelname)s] %(message)s')
        
        # Configure logging
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("Launch manager started")
    
    def _create_pid_file(self):
        """Create PID file and register cleanup"""
        try:
            # Write current PID to file
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            
            # Register cleanup function
            atexit.register(self._cleanup_pid_file)
            
            self.logger.info(f"Created PID file: {self.pid_file}")
        except Exception as e:
            self.logger.error(f"Failed to create PID file: {e}")
    
    def _cleanup_pid_file(self):
        """Clean up PID file on exit"""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
                self.logger.info(f"Removed PID file: {self.pid_file}")
        except Exception as e:
            self.logger.error(f"Failed to remove PID file: {e}")
    
    def _register_builtin_commands(self):
        """Register built-in commands"""
        self.register_command('status', self.cmd_status, 
                            "Show status of all managed processes")
        self.register_command('restart-manager', self.cmd_restart_manager,
                            "Restart the launch manager")
        self.register_command('shutdown', self.cmd_shutdown,
                            "Shutdown the launch manager and all processes")
        self.register_command('list-commands', self.cmd_list_commands,
                            "List all available commands with descriptions")
        self.register_command('help', self.cmd_help,
                            "Show help for a specific command")
    
    def _load_plugin_commands(self):
        """Load commands from the commands directory"""
        commands_dir = Path(__file__).parent / 'commands'
        if not commands_dir.exists():
            commands_dir.mkdir(exist_ok=True)
            return
        
        for cmd_file in commands_dir.glob('*.py'):
            if cmd_file.name.startswith('_'):
                continue
                
            try:
                # Load the module
                spec = importlib.util.spec_from_file_location(
                    cmd_file.stem, cmd_file
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Look for command function
                    if hasattr(module, 'command'):
                        cmd_func = getattr(module, 'command')
                        cmd_name = cmd_file.stem.replace('_', '-')
                        
                        # Get help text from docstring or module docstring
                        help_text = inspect.getdoc(cmd_func) or inspect.getdoc(module) or f"Command: {cmd_name}"
                        
                        # Store the module for help generation
                        self.command_modules[cmd_name] = module
                        
                        self.register_command(cmd_name, cmd_func, help_text)
                        self.logger.info(f"Loaded command: {cmd_name}")
                        
            except Exception as e:
                print(f"Error loading command {cmd_file}: {e}")
    
    def register_command(self, name: str, func: Callable, help_text: str = ""):
        """Register a command with the manager"""
        self.commands[name] = func
        self.command_help[name] = help_text
    
    def cmd_status(self, args: list) -> Dict[str, Any]:
        """Show status of all managed processes"""
        status = {}
        for name, info in self.process_info.items():
            proc = self.processes.get(name)
            if proc:
                try:
                    proc.poll()
                    if proc.returncode is None:
                        status[name] = {
                            'status': 'running',
                            'pid': proc.pid,
                            'command': info['command'],
                            'started': info['started']
                        }
                    else:
                        status[name] = {
                            'status': 'stopped',
                            'return_code': proc.returncode,
                            'command': info['command']
                        }
                except:
                    status[name] = {'status': 'unknown', 'command': info['command']}
            else:
                status[name] = {'status': 'not started', 'command': info['command']}
        
        return {'success': True, 'processes': status}
    
    def cmd_restart_manager(self, args: list) -> Dict[str, Any]:
        """Restart the launch manager"""
        try:
            # Find the parent launch.sh process
            current_process = psutil.Process(os.getpid())
            parent_process = current_process.parent()
            
            if parent_process and 'launch.sh' in ' '.join(parent_process.cmdline()):
                # Send SIGHUP to launch.sh
                parent_process.send_signal(signal.SIGHUP)
                return {
                    'success': True, 
                    'message': 'Manager restart requested via SIGHUP. The manager should restart automatically.'
                }
            else:
                return {
                    'success': False,
                    'error': 'Could not find launch.sh parent process.\n\n' +
                            'To manually restart the manager:\n' +
                            '1. Find the launch.sh process: ps aux | grep launch.sh\n' +
                            '2. Send SIGHUP: kill -HUP <pid>\n' +
                            '3. Or restart the launch.sh process in your terminal'
                }
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to send restart signal: {e}\n\n' +
                        'To manually restart the manager, send SIGHUP to the launch.sh process.'
            }
    
    def cmd_shutdown(self, args: list) -> Dict[str, Any]:
        """Shutdown the launch manager and all processes"""
        # Stop all processes
        for name in list(self.processes.keys()):
            self.stop_process(name)
        
        self.running = False
        return {'success': True, 'message': 'Shutdown initiated'}
    
    def cmd_list_commands(self, args: list) -> Dict[str, Any]:
        """List all available commands"""
        commands = {}
        for name, help_text in self.command_help.items():
            commands[name] = help_text
        
        return {'success': True, 'commands': commands}
    
    def cmd_help(self, args: list) -> Dict[str, Any]:
        """Show help for a specific command"""
        if not args:
            return {'success': False, 'error': 'Please specify a command name'}
        
        cmd_name = args[0]
        if cmd_name in self.command_help:
            help_text = self.command_help[cmd_name]
            
            # Check if command has a get_parser function
            if cmd_name in self.command_modules:
                module = self.command_modules[cmd_name]
                if hasattr(module, 'get_parser'):
                    try:
                        parser = module.get_parser()
                        # Capture parser help
                        import io
                        help_buffer = io.StringIO()
                        parser.print_help(file=help_buffer)
                        detailed_help = help_buffer.getvalue()
                        help_text = f"{help_text}\n\n{detailed_help}"
                    except:
                        pass
            
            return {
                'success': True,
                'command': cmd_name,
                'help': help_text
            }
        else:
            return {'success': False, 'error': f'Unknown command: {cmd_name}'}
    
    def stop_process(self, name: str):
        """Stop a managed process"""
        if name in self.processes:
            proc = self.processes[name]
            termination_timeout = self.config.get('process', {}).get('termination_timeout', 5)
            try:
                proc.terminate()
                proc.wait(timeout=termination_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
            except:
                pass
            finally:
                del self.processes[name]
    
    def handle_command(self, command: str, args: list) -> Dict[str, Any]:
        """Handle incoming commands"""
        if command in self.commands:
            try:
                # Check if it's a built-in command (method) or plugin command
                cmd_func = self.commands[command]
                if hasattr(cmd_func, '__self__'):
                    # It's a method, call without self
                    return cmd_func(args)
                else:
                    # It's a plugin function, pass self as first argument
                    return cmd_func(self, args)
            except Exception as e:
                import traceback
                traceback.print_exc()
                return {'success': False, 'error': str(e)}
        else:
            return {'success': False, 'error': f'Unknown command: {command}'}
    
    def start_socket_server(self):
        """Start the Unix socket server"""
        # Remove existing socket
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        # Create socket
        server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_socket.bind(self.socket_path)
        server_socket.listen(5)
        
        print(f"Launch manager listening on {self.socket_path}")
        
        while self.running:
            try:
                server_socket.settimeout(self.socket_timeout)
                client, _ = server_socket.accept()
                threading.Thread(target=self.handle_client, args=(client,)).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Socket error: {e}")
        
        server_socket.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
    
    def handle_client(self, client_socket):
        """Handle client connections"""
        try:
            # Try to read length prefix first (new protocol)
            # Peek at first 8 bytes to check if it's the new protocol
            client_socket.settimeout(0.1)  # Short timeout for peek
            try:
                first_bytes = client_socket.recv(8, socket.MSG_PEEK)
                if len(first_bytes) == 8:
                    # Try to interpret as length prefix
                    potential_length = int.from_bytes(first_bytes, 'big')
                    # Sanity check - if it's a reasonable length, use new protocol
                    if 0 < potential_length < 10_000_000:  # Max 10MB
                        # New protocol with length prefix
                        client_socket.settimeout(self.socket_timeout)
                        
                        # Read the actual length prefix
                        length_data = b''
                        while len(length_data) < 8:
                            chunk = client_socket.recv(8 - len(length_data))
                            if not chunk:
                                raise ConnectionError("Connection closed while reading length prefix")
                            length_data += chunk
                        
                        request_length = int.from_bytes(length_data, 'big')
                        
                        # Read exact request length
                        request_data = b''
                        while len(request_data) < request_length:
                            chunk = client_socket.recv(min(4096, request_length - len(request_data)))
                            if not chunk:
                                raise ConnectionError("Connection closed while reading request")
                            request_data += chunk
                        
                        request = json.loads(request_data.decode())
                        command = request.get('command', '')
                        args = request.get('args', [])
                        
                        response = self.handle_command(command, args)
                        response_data = json.dumps(response).encode()
                        
                        # Log large responses
                        if len(response_data) > 1_000_000:
                            self.logger.info(f"Sending large response: {len(response_data):,} bytes")
                        
                        # Send length prefix followed by response
                        length_prefix = len(response_data).to_bytes(8, 'big')
                        client_socket.sendall(length_prefix + response_data)
                        return
            except socket.timeout:
                pass
            
            # Fall back to old protocol (direct JSON)
            client_socket.settimeout(self.socket_timeout)
            # Read until we get complete JSON
            data = b''
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                data += chunk
                try:
                    # Try to parse JSON to see if we have complete data
                    json.loads(data.decode())
                    break
                except:
                    # Not complete yet, keep reading
                    continue
            
            if data:
                request = json.loads(data.decode())
                command = request.get('command', '')
                args = request.get('args', [])
                
                response = self.handle_command(command, args)
                response_data = json.dumps(response).encode()
                
                # For large responses in old protocol, send in chunks
                sent = 0
                while sent < len(response_data):
                    chunk_size = client_socket.send(response_data[sent:sent + 65536])
                    sent += chunk_size
        except Exception as e:
            error_response = {'success': False, 'error': str(e)}
            error_data = json.dumps(error_response).encode()
            
            # Send error using new protocol with length prefix
            try:
                length_prefix = len(error_data).to_bytes(8, 'big')
                client_socket.send(length_prefix + error_data)
            except:
                # If that fails, try old protocol
                try:
                    client_socket.send(error_data)
                except:
                    pass
        finally:
            client_socket.close()

def main():
    manager = ProcessManager()
    
    # Handle signals
    def signal_handler(signum, frame):
        print("\nShutting down...")
        manager.running = False
        manager._cleanup_pid_file()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start the socket server
    manager.start_socket_server()

if __name__ == '__main__':
    main()