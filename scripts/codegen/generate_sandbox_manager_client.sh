#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_DIR}"
uv run --package sandbox-manager cara-sandbox-manager-schema
uv run httpxgen \
    sandbox_manager/schema/openapi.json \
    generated/sandbox_manager_client/src/sandbox_manager_client \
    --package-name sandbox_manager_client \
    --client-name SandboxManagerClient \
    --http-client httpx2

# Format first: generated union TypeAdapter lines exceed the length limit until wrapped.
uv run ruff format generated/sandbox_manager_client/src
uv run ruff check --fix generated/sandbox_manager_client/src
