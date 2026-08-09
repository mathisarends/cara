#!/usr/bin/env bash
# Discover the Philips Hue bridge and create an app key, so you can set
# HUE_BRIDGE_IP and HUE_APP_KEY in your .env. Requires pressing the bridge's
# physical link button when prompted.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run python - <<'PY'
from hueify.onboarding import setup

setup()
PY
