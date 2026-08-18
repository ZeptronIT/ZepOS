#!/bin/bash
# fetch_icons.sh - Simple wrapper for fetch_icons.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to script directory so Python can find icon_definitions.py
cd "$SCRIPT_DIR"

# Run the Python script
python3 fetch_icons.py

