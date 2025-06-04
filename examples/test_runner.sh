#!/bin/bash

# Test script for Claude runner

echo "Testing Claude runner..."

# Simple test
./claudecontroller runner "What is 2+2?"

# Test with name
./claudecontroller runner --name math-test "Calculate the square root of 144"

# Test with context file
echo "def factorial(n): return 1 if n <= 1 else n * factorial(n-1)" > /tmp/test_context.py
./claudecontroller runner --context-file /tmp/test_context.py "Explain this code and calculate factorial(5)"

# Test with report
./claudecontroller runner --report /tmp/claude_report.md "Write a haiku about programming"

# Check status
sleep 2
./claudecontroller runner-status

echo "Tests complete!"