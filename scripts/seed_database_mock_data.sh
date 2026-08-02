#!/usr/bin/env bash
set -euo pipefail

uv run python scripts/seed_database_mock_data.py "$@"
