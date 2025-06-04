#!/bin/bash
# Claude wrapper script that ensures proper environment

# Debug logging (uncomment for troubleshooting)
# echo "[WRAPPER] Node type: $CLAUDECONTROLLER_NODE_TYPE" >&2
# echo "[WRAPPER] Claude path: $CLAUDECONTROLLER_CLAUDE_PATH" >&2

# Otherwise, set up the environment based on node type
case "$CLAUDECONTROLLER_NODE_TYPE" in
    "nvm")
        if [ -n "$CLAUDECONTROLLER_NVM_SCRIPT" ] && [ -f "$CLAUDECONTROLLER_NVM_SCRIPT" ]; then
            source "$CLAUDECONTROLLER_NVM_SCRIPT"
        elif [ -f ~/.nvm/nvm.sh ]; then
            source ~/.nvm/nvm.sh
        fi
        ;;
    
    "asdf")
        if [ -n "$CLAUDECONTROLLER_NVM_SCRIPT" ] && [ -f "$CLAUDECONTROLLER_NVM_SCRIPT" ]; then
            source "$CLAUDECONTROLLER_NVM_SCRIPT"
        elif [ -f ~/.asdf/asdf.sh ]; then
            source ~/.asdf/asdf.sh
        fi
        ;;
    
    "fnm")
        # fnm typically sets up PATH via eval
        if command -v fnm >/dev/null 2>&1; then
            eval "$(fnm env)"
        fi
        ;;
    
    "volta")
        # Volta typically manages PATH automatically
        if [ -n "$VOLTA_HOME" ]; then
            export PATH="$VOLTA_HOME/bin:$PATH"
        elif [ -d ~/.volta ]; then
            export PATH="$HOME/.volta/bin:$PATH"
        fi
        ;;
    
    "n")
        # n typically installs to /usr/local/bin or similar
        # Usually no special setup needed as it's in PATH
        ;;
    
    "system"|"unknown"|*)
        # Try common locations if not in PATH
        for dir in /usr/local/bin /usr/bin ~/.local/bin ~/bin; do
            if [ -x "$dir/claude" ]; then
                exec "$dir/claude" "$@"
            fi
        done
        ;;
esac

# Execute claude with all arguments
if [ -n "$CLAUDECONTROLLER_CLAUDE_PATH" ] && [ -x "$CLAUDECONTROLLER_CLAUDE_PATH" ]; then
    # If we have a direct path to claude, use it
    exec "$CLAUDECONTROLLER_CLAUDE_PATH" "$@"
    exit ${?}
else
    exec claude "$@"
fi
