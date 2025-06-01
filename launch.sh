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

# Simple wrapper that monitors for manager restart requests
while true; do
    python "$SCRIPT_DIR/launch-manager.py" &
    MANAGER_PID=$!
    while kill -0 $MANAGER_PID 2>/dev/null && [ ! -f "$SCRIPT_DIR/.restart-manager" ]; do
        sleep 1
    done
    [ -f "$SCRIPT_DIR/.restart-manager" ] && rm "$SCRIPT_DIR/.restart-manager" && kill $MANAGER_PID 2>/dev/null
done