# ClaudeController Testing Plan

## Overview
Comprehensive testing plan for all ClaudeController features and TODO items. This document ensures systematic validation of every implementation with concrete test scenarios and pass/fail criteria.

## Testing Methodology

### Test Data Creation
- Use controlled `Task()` calls with known expected outputs
- Create specific test scenarios with predictable token usage
- Generate test sessions with known todo lifecycles
- Document expected vs actual results for all tests

### Validation Criteria
- All token calculations must be mathematically correct
- All features must work with real Claude Code session data
- Output formats must match specifications exactly
- No regressions in existing functionality

## Token Analysis Features Testing

### 1. Basic Token Usage (`./claudecontroller tokens`)

**Test Case 1.1: Basic token display**
```bash
# Setup: Use current session
./claudecontroller tokens

# Expected: Shows current context usage with percentages
# Validation: Verify numbers add up correctly, percentages calculated properly
```

**Test Case 1.2: Brief token display**
```bash
./claudecontroller tokens --brief

# Expected: Single line format: "X,XXX / 165,000 (XX.X%)"
# Validation: Format matches specification exactly
```

**Test Case 1.3: JSON output**
```bash
./claudecontroller tokens --json

# Expected: Valid JSON with all token fields
# Validation: JSON parses correctly, contains required fields
```

### 2. Task Chain Analysis (`tokens --tasks`)

**CRITICAL BUG TO FIX FIRST:** Token calculation is wrong - uses cumulative totals instead of deltas

**Test Case 2.1: Task chain token calculation**
```bash
# Setup: Create controlled task chain
Task("Simple test task for token measurement")

# Execute and validate
./claudecontroller tokens --tasks

# Expected: Reasonable token usage (not millions)
# Validation: 
# - Task tokens = end_cumulative - start_cumulative
# - Total should be < 200K (context window limit)
# - Individual task tokens should be reasonable (100-10K range)
```

**Test Case 2.2: Multiple task chains**
```bash
# Setup: Create multiple distinct task chains
Task("First test task")
Task("Second test task") 

# Execute and validate
./claudecontroller tokens --tasks

# Expected: Separate chains with correct token attribution
# Validation: Each chain shows distinct start/end points
```

**Test Case 2.3: Task hierarchy validation**
```bash
# Validation: Verify parent-child relationships are correct
# Check that isSidechain=true tasks are properly grouped
# Ensure UUID chains are followed correctly
```

### 3. Todo Analysis (`tokens --todos`)

**Test Case 3.1: Todo lifecycle tracking**
```bash
# Setup: Create todos with known lifecycle
TodoWrite([
    {"id": "test1", "content": "Test todo 1", "status": "pending", "priority": "high"},
    {"id": "test1", "content": "Test todo 1", "status": "in_progress", "priority": "high"},
    {"id": "test1", "content": "Test todo 1", "status": "completed", "priority": "high"}
])

# Execute and validate
./claudecontroller tokens --todos

# Expected: Shows completed todo with token delta calculation
# Validation: Token usage = tokens_at_completion - tokens_at_start
```

**Test Case 3.2: Brief todos format**
```bash
./claudecontroller tokens --todos --brief

# Expected: Format per specification:
# # {session_id}
# - Todo item -- XXXtkn -- 00h15m23s
# Validation: Exact format match, proper token/duration formatting
```

**Test Case 3.3: Unknown todo status investigation**
```bash
# Identify todos showing "unknown" status despite proper lifecycle
# Root cause analysis of why in_progress → completed flow isn't tracked
# Fix tracking logic and verify proper status progression
```

### 4. Unified Analysis (`tokens --all`)

**Test Case 4.1: Combined task and todo display**
```bash
./claudecontroller tokens --all

# Expected: Shows both task chains and todos in unified view
# Validation: Both sections present, combined totals correct
```

**Test Case 4.2: Session summary validation**
```bash
# Validation: Combined totals = task_tokens + todo_tokens
# Verify session summaries are mathematically correct
```

## Feature Implementation Testing

### 5. Unique Todo/Task IDs

**Test Case 5.1: ID uniqueness**
```bash
# Create todos with same content but different contexts
# Verify hash-based IDs are unique across sessions
# Test ID persistence across todo lifecycle events
```

**Test Case 5.2: Hash consistency**
```bash
# Same todo content should generate same ID within session
# Different sessions should have different IDs for same content
```

### 6. PID Management

**Test Case 6.1: PID subcommand**
```bash
./claudecontroller pid

# Expected: Shows current manager PID
# Validation: PID matches actual running process
```

**Test Case 6.2: PID file management**
```bash
# Check .pid file exists after manager start
# Verify .pid file deleted on manager exit
# Test atexit handler functionality
```

**Test Case 6.3: PID in log filenames**
```bash
# Verify log format: launch-manager_{timestamp}_{pid}.log
# Check PID in filename matches actual process PID
```

### 7. Help System Enhancement

**Test Case 7.1: Subcommand listing**
```bash
./claudecontroller --help

# Expected: Lists all available subcommands from commands/ directory
# Validation: All plugin files are discovered and listed
```

**Test Case 7.2: Command descriptions**
```bash
# Verify brief descriptions are shown for each command
# Check that help output is properly formatted
```

## Bug Fix Testing

### 8. Token Calculation Fix (CRITICAL)

**Test Case 8.1: Cumulative token logic**
```bash
# Create test session with known token progression
# Manually verify cumulative totals in JSONL
# Test delta calculation: task_tokens = end_cumulative - start_cumulative
```

**Test Case 8.2: Subtask token calculation**
```bash
# Test nested task token attribution
# Verify subtask tokens = current_line_total - previous_line_total
```

**Test Case 8.3: Real session validation**
```bash
# Test against actual Claude Code sessions
# Verify total tokens never exceed context window limits
# Check that token totals are reasonable and make sense
```

### 9. Todo Status Tracking Fix

**Test Case 9.1: Lifecycle progression**
```bash
# Test pending → in_progress → completed flow
# Verify each status change is properly detected
# Fix logic that's causing "unknown" status
```

## Integration Testing

### 10. End-to-End Workflow Tests

**Test Case 10.1: Complete feature workflow**
```bash
# 1. Start with clean session
# 2. Create todos with TodoWrite
# 3. Execute Task() calls
# 4. Run all token commands (--tasks, --todos, --all, --brief)
# 5. Verify all outputs are consistent and correct
```

**Test Case 10.2: Cross-session testing**
```bash
# Test with multiple sessions (-n flag)
# Verify session isolation and proper aggregation
```

## Performance Testing

### 11. Large Session Handling

**Test Case 11.1: Large JSONL files**
```bash
# Test with sessions containing thousands of lines
# Verify parsing performance and memory usage
# Check for timeouts or crashes
```

## Regression Testing

### 12. Backwards Compatibility

**Test Case 12.1: Existing functionality**
```bash
# Verify all existing commands still work
# Test bash, runner, streamfile commands
# Ensure no breaking changes to existing APIs
```

## Test Execution Plan

### Phase 1: Critical Bug Fixes
1. Fix token calculation logic (Test Cases 8.1-8.3)
2. Fix todo status tracking (Test Case 9.1)
3. Validate fixes with real data

### Phase 2: Feature Validation
1. Test all implemented token flags (Test Cases 1-4)
2. Validate output formats match specifications
3. Test edge cases and error conditions

### Phase 3: New Feature Testing
1. Test PID management (Test Cases 6.1-6.3)
2. Test help system (Test Cases 7.1-7.2)
3. Test unique ID generation (Test Cases 5.1-5.2)

### Phase 4: Integration & Performance
1. End-to-end workflow testing (Test Cases 10.1-10.2)
2. Performance testing (Test Case 11.1)
3. Regression testing (Test Case 12.1)

## Success Criteria

### Must Pass 100%:
- ✅ All token calculations are mathematically correct
- ✅ All output formats match specifications exactly
- ✅ No functionality regressions
- ✅ All edge cases handled properly
- ✅ Performance is acceptable for normal usage

### Documentation Requirements:
- Document all test results
- Record any deviations from expected behavior
- Update implementation based on test findings
- Create reproducible test scenarios

## Failure Handling

If any test fails:
1. **STOP immediately** - do not continue until fixed
2. Analyze root cause of failure
3. Implement fix with proper validation
4. Re-run failed test and all related tests
5. Document fix and update test if needed

**DO NOT STOP until ALL tests pass 100%**

## Test Data Location

Test sessions and data should be stored in:
- `tests/` directory (to be created)
- Known good JSONL files for validation
- Expected output files for comparison
- Test scripts for automated execution