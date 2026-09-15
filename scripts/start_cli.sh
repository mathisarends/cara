#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Interactive console client against a running gateway.
# Pass --events to see the raw session event stream, --session <uuid> to resume.
exec uv run --package cli cara-chat "$@"
