#!/usr/bin/env bash
# Discover Sonos speakers on the local network and print their IP addresses,
# so you can pin one as SONOS_IP_ADDRESS in your .env and skip the network scan.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run --extra sonos python - <<'PY'
import soco

zones = soco.discover(timeout=5)
if not zones:
    raise SystemExit("No Sonos devices found on the network.")

ordered = sorted(zones, key=lambda zone: zone.player_name)
print(f"{'SPEAKER':<28} IP ADDRESS")
for zone in ordered:
    print(f"{zone.player_name:<28} {zone.ip_address}")

print("\nAdd the speaker you want to your .env, e.g.:")
print(f"  SONOS_IP_ADDRESS={ordered[0].ip_address}")
PY
