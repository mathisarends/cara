"""Activate the configured voice client from an additional external source."""

import asyncio
import logging
import os

from voice import ExternalActivationSource, VoiceClient, VoiceClientConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = float(os.environ.get("CARA_VOICE_ACTIVATION_INTERVAL", "30"))
_LISTEN_SECONDS = 5.0


async def main() -> None:
    config = VoiceClientConfig.from_yaml()
    activation = ExternalActivationSource()
    client = VoiceClient(config, activation_sources=(activation,))
    async with client:
        heartbeat = asyncio.create_task(
            _trigger_periodically(activation),
            name="example-heartbeat",
        )
        try:
            await client.run()
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)


async def _trigger_periodically(activation: ExternalActivationSource) -> None:
    while True:
        await asyncio.sleep(_INTERVAL_SECONDS)
        logger.info("Button: opening the microphone without a wake word")
        await activation.activate(speech_start_timeout=_LISTEN_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
