#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}"
# Importing sandbox_manager.app builds its module-level ASGI app eagerly, which
# requires a token even though schema export never talks to the sandbox itself.
CARA_SANDBOX_TOKEN=schema-export \
    uv run --package sandbox-manager cara-sandbox-manager-schema
uv run httpxgen \
    sandbox_manager/schema/openapi.json \
    generated/sandbox_manager_client/src/sandbox_manager_client \
    --package-name sandbox_manager_client \
    --client-name SandboxManagerClient \
    --http-client httpx2

uv run ruff check --fix generated/sandbox_manager_client/src
uv run ruff format generated/sandbox_manager_client/src
