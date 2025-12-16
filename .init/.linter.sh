#!/bin/bash
cd /tmp/kavia/workspace/code-generation/flashcard-study-app-3914-3923/flashcard_backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

