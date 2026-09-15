#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly REST_CLIENT_SRC="generated/gateway_rest_client/src"

cd "${PROJECT_DIR}"
uv run --package gateway-server cara-gateway-schema
uv run --package gateway-server cara-gateway-rpc-client-generate \
    gateway/schema/gateway.openrpc.json
uv run httpxgen \
    gateway/schema/openapi.json \
    "${REST_CLIENT_SRC}/gateway_rest_client" \
    --package-name gateway_rest_client \
    --client-name GatewayRestClient \
    --http-client httpx2

# Format first: generated union TypeAdapter lines exceed the length limit until wrapped.
uv run ruff format "${REST_CLIENT_SRC}"
uv run ruff check --fix "${REST_CLIENT_SRC}"
