#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

uv run gateway-migrate

# No --reload by default: on Windows uvicorn runs reloaded servers on a
# SelectorEventLoop, which has no subprocess support, so the agent cannot start
# its Docker sandbox and every turn using the bash tool fails instantly.
# Set CARA_RELOAD=1 when editing the gateway itself and the agent is not needed.
if [[ "${CARA_RELOAD:-0}" == "1" ]]; then
    echo "CARA_RELOAD=1: hot reload on, the agent's bash tool will not work." >&2
    exec uv run uvicorn gateway.app:app --reload \
        --reload-dir gateway/server/src \
        --reload-dir agent/src \
        --reload-dir llm/src \
        "$@"
fi

exec uv run cara-gateway
