#!/bin/bash
# Activate virtual environment for self-tester-automation

source venv/bin/activate
echo "✓ Virtual environment activated"
echo "Python: $(which python)"
echo "Python version: $(python --version)"
