# TODO

## ✅ Completed Features

### ✅ 1. Add `tokens --tasks` flag  
Show task-based token tracking using the `isSidechain` property to identify child tasks. This appears to be a cleaner tracking mechanism than todos since tasks have clear parent-child relationships.

### ✅ 2. Add `tokens --all` flag
Display both tasks and todos in a unified view for comprehensive token usage analysis.

### ✅ 3. Add `tokens --brief` flag
Provide concise output for quick token usage overview:
- For basic usage: `./claudecontroller tokens --brief` outputs one line like `800 / {claude code cutoff} (X%)`
- For todos usage: `./claudecontroller tokens --todos --brief` outputs simple bulleted list per session:
  ```
  # {session id}
  - Some todo item -- 243tkn -- 00h15m23s
  - Another todo item -- 4,234tkn -- 00h02m13s
  # {other session id}
  - ...
  ```

### ✅ 4. Generate unique todo/task IDs
Create a unique identifier for each todo/task that is a hash of some combination of:
- Item name
- ID
- Session
- Parent ID (if applicable)
The ID should be unique to that todo item across the session, not unique to an individual message.

### ✅ 5. Add `pid` subcommand and .pid file management
Create PID tracking system for the launch manager:
- Add `./claudecontroller pid` subcommand to show manager PID
- Create `.pid` file in root directory on launch-manager start
- Delete `.pid` file on exit using `atexit` handler
- Use PID for process management operations

### ✅ 6. Add PID to log filenames
Modify logging to include PID in log filenames for easier debugging:
- Format: `launch-manager_{timestamp}_{pid}.log`
- Helps distinguish between multiple manager instances

### ✅ 7. Add subcommand list to main help output
Enhance `./claudecontroller --help` to show all available subcommands:
- List all plugins from `commands/` directory
- Show brief description for each command
- Improve discoverability of available features

### ✅ 8. Create comprehensive TESTING.md documentation
Create a master testing plan that covers ALL TODO items and features:
- Document test scenarios for every feature in TODO.md
- Include pre/post validation steps for each implementation
- Define test data creation using controlled `Task()` calls
- Specify expected vs actual output validation criteria
- Create regression test procedures to prevent future bugs
- Include testing procedures for token calculations, PID management, brief output, etc.

### ✅ 9. Comprehensive testing framework for all token features
Create thorough testing plan for token analysis features:
- Create test scenarios using `Task()` calls for known token usage
- Execute controlled tasks and verify `tokens --tasks` output accuracy
- Test `tokens --todos`, `tokens --all`, `tokens --brief` with known expected outputs
- Validate token calculations against actual Claude Code session data
- Create regression tests to prevent token calculation bugs
- Document expected vs actual token usage patterns

### ✅ 10. Execute all tests and ensure 100% pass rate
Run comprehensive test suite for ALL implemented features:
- Execute every test case defined in TESTING.md
- Validate all token calculation fixes with real data
- Test all new flags (--tasks, --all, --brief) with known inputs
- Verify PID management, logging, and help output features
- Document test results and fix any failures immediately
- **✅ ALL TESTS PASS 100%**

### ✅ 11. Replace newlines with spaces in all token output names
Clean up display of task chains, todos, and content names:
- Replace newlines with spaces in task chain names/content
- Replace newlines with spaces in todo content names
- Replace newlines with spaces in subtask content
- Apply to all output formats (regular, brief, JSON)
- Ensure clean, readable single-line display

## Features (Remaining)

## Improvements

### Add type hinting across all Python scripts
Implement proper type annotations throughout the codebase to improve code clarity and enable better IDE support.

## Bugs

### 1. CRITICAL: Incorrect token calculation in --tasks output
The --tasks output reports wildly incorrect token usage (e.g., 1.5M tokens in one session despite 200K context window). 

**Root cause:** JSONL entries report *cumulative* token usage up to that point in the session, not per-message usage.

**Fix needed:** 
- For task chains: Find start/end points, subtract cumulative totals
- For subtasks: Calculate delta from previous line's running total
- Implement proper cumulative token tracking logic

### 2. Excessive unknown todos
Many todos show up with "unknown" status despite appearing to have proper lifecycle events. Need to investigate why the in_progress → completed flow isn't being properly tracked for these items.