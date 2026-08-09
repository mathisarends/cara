#!/usr/bin/env bash
# Regenerate src/gateway_client/models.py from the OpenAPI spec.
#
#   ./generate_client.sh                              # use the checked-in openapi.json
#   ./generate_client.sh --url http://127.0.0.1:8000  # refresh the snapshot first
set -euo pipefail
cd "$(dirname "$0")/../.."

uv run python gateway_client/scripts/generate_client.py "$@"
