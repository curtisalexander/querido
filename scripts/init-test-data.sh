#!/usr/bin/env bash
# Initialize test databases with sample data.
# Run from the project root: ./scripts/init-test-data.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
uv run python scripts/init_test_data.py
