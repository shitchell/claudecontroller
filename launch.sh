#!/bin/bash
# Claude Controller Launch Manager
# Automatically sets up symlink and keeps manager running

# Get the directory where launch.sh was called from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# Check if symlink exists in parent directory
if [ ! -L "$PARENT_DIR/claudecontroller" ]; then
    echo "Creating claudecontroller symlink in $PARENT_DIR..."
    ln -sf "$SCRIPT_DIR/claudecontroller" "$PARENT_DIR/claudecontroller"
    echo "✓ Symlink created: $PARENT_DIR/claudecontroller -> $SCRIPT_DIR/claudecontroller"
fi

# Variables for managing restart
MANAGER_PID=""
RESTART_REQUESTED=false

# Function to start the manager
start_manager() {
    python "$SCRIPT_DIR/launch-manager.py" &
    MANAGER_PID=$!
    echo "Launch manager started with PID: $MANAGER_PID"
}

# Function to stop the manager
stop_manager() {
    if [ -n "$MANAGER_PID" ] && kill -0 $MANAGER_PID 2>/dev/null; then
        echo "Stopping launch manager (PID: $MANAGER_PID)..."
        kill $MANAGER_PID 2>/dev/null
        wait $MANAGER_PID 2>/dev/null
    fi
}

# Trap for restart on SIGHUP
trap 'RESTART_REQUESTED=true' SIGHUP

# Trap for clean shutdown
trap 'echo "Shutting down..."; stop_manager; exit 0' SIGINT SIGTERM

# Main loop
while true; do
    start_manager
    
    # Wait for manager to exit or restart signal
    while kill -0 $MANAGER_PID 2>/dev/null; do
        if [ "$RESTART_REQUESTED" = true ]; then
            echo "Restart requested via SIGHUP"
            RESTART_REQUESTED=false
            stop_manager
            break
        fi
        sleep 1
    done
    
    # If manager died unexpectedly, wait a bit before restarting
    if kill -0 $MANAGER_PID 2>/dev/null; then
        echo "Manager stopped, restarting..."
    else
        echo "Manager died unexpectedly, restarting in 2 seconds..."
        sleep 2
    fi
done