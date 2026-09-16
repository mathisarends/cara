"""Run voice.yml with audio.output.type set to sonos."""

import asyncio
import logging

from voice import VoiceSessionFactory

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    factory = VoiceSessionFactory.from_yaml()
    session = await factory.create()
    async with session:
        await session.run()


if __name__ == "__main__":
    asyncio.run(main())
