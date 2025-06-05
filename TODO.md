# TODO

## Features

### 1. Add `tokens --tasks` flag
Show task-based token tracking using the `isSidechain` property to identify child tasks. This appears to be a cleaner tracking mechanism than todos since tasks have clear parent-child relationships.

### 2. Add `tokens --all` flag
Display both tasks and todos in a unified view for comprehensive token usage analysis.

## Improvements

### Add type hinting across all Python scripts
Implement proper type annotations throughout the codebase to improve code clarity and enable better IDE support.

## Bugs

### 1. Excessive unknown todos
Many todos show up with "unknown" status despite appearing to have proper lifecycle events. Need to investigate why the in_progress → completed flow isn't being properly tracked for these items.