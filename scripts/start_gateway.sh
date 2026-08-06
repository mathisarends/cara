#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

uv run uvicorn gateway.main:app --reload "$@"
