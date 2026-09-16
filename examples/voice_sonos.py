"""Run voice.yml with audio.output.type set to sonos."""

import asyncio
import logging
import os

from voice import VoiceSessionFactory

# The root level stays at INFO: websockets logs every media frame at DEBUG.
logging.basicConfig(level=logging.INFO)
# CARA_VOICE_LOG_LEVEL=DEBUG traces every event on the voice bus.
logging.getLogger("voice").setLevel(os.environ.get("CARA_VOICE_LOG_LEVEL", "INFO"))


async def main() -> None:
    factory = VoiceSessionFactory.from_yaml()
    session = await factory.create()
    async with session:
        await session.run()


if __name__ == "__main__":
    asyncio.run(main())
