#!/usr/bin/env bash
# Discover Sonos speakers on the local network and print their IP addresses,
# so you can pin one as SONOS_IP_ADDRESS in your .env and skip the network scan.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run python - <<'PY'
import asyncio

from sonosify import SonosController


async def main() -> None:
    system = await SonosController().discover()
    speakers = sorted(system.speakers, key=lambda speaker: speaker.room_name)
    if not speakers:
        raise SystemExit("No Sonos devices found on the network.")

    print(f"{'SPEAKER':<28} IP ADDRESS")
    for speaker in speakers:
        print(f"{speaker.room_name:<28} {speaker.ip}")

    print("\nAdd the speaker you want to your .env, e.g.:")
    print(f"  SONOS_IP_ADDRESS={speakers[0].ip}")


asyncio.run(main())
PY
