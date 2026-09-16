"""Run the voice client using the audio and integrations from voice.yml."""

import asyncio
import logging

from voice import VoiceClient, VoiceClientConfig

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    config = VoiceClientConfig.from_yaml()
    client = VoiceClient(config)
    async with client:
        await client.run()


if __name__ == "__main__":
    asyncio.run(main())
