#!/usr/bin/env bash
set -euo pipefail

uv run python scripts/delete_database_mock_data.py "$@"
