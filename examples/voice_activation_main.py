"""Activate the configured voice session from an additional external source."""

import asyncio
import logging
import os

from voice import ExternalActivationSource, VoiceSessionFactory

# The root level stays at INFO: websockets logs every media frame at DEBUG.
logging.basicConfig(level=logging.INFO)
# CARA_VOICE_LOG_LEVEL=DEBUG traces every event on the voice bus.
logging.getLogger("voice").setLevel(os.environ.get("CARA_VOICE_LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = float(os.environ.get("CARA_VOICE_ACTIVATION_INTERVAL", "30"))
_LISTEN_SECONDS = 5.0


async def main() -> None:
    activation = ExternalActivationSource()
    factory = VoiceSessionFactory.from_yaml(activation_sources=(activation,))
    session = await factory.create()
    async with session:
        heartbeat = asyncio.create_task(
            _trigger_periodically(activation),
            name="example-heartbeat",
        )
        try:
            await session.run()
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
