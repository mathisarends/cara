#!/usr/bin/env bash
# Discover the Philips Hue bridge and create an app key, so you can set
# HUE_BRIDGE_IP and HUE_APP_KEY in your .env. Requires pressing the bridge's
# physical link button when prompted.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run python - <<'PY'
import asyncio

from hueify.onboarding import discover_bridges, register_app_key


async def main() -> None:
    bridges = await discover_bridges()
    bridge = bridges[0]
    if len(bridges) > 1:
        print(f"Found {len(bridges)} bridges; using the first ({bridge.internalipaddress}).")

    ip = bridge.internalipaddress
    print(f"Found Hue bridge at {ip}.")
    print("Press the link button on top of the bridge now (you have 60 seconds)...")

    app_key = await register_app_key(ip, device_type="cara")

    print("\nAdd these to your .env:")
    print(f"  HUE_BRIDGE_IP={ip}")
    print(f"  HUE_APP_KEY={app_key}")


asyncio.run(main())
PY
