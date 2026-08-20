#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Interactive console client against a gateway started via scripts/start_gateway.sh.
# Pass --events to see the raw session event stream, --session <uuid> to resume.
exec uv run --package cli cara-chat "$@"
