"""Run a standalone voice session straight against the Gateway, without a Room.

Reads voice.yml from the working directory, e.g. `uv run examples/voice/main.py`
from the repository root.
"""

import asyncio
import logging
import os

from voice import VoiceSessionFactory

# The root level stays at INFO: websockets logs every media frame at DEBUG.
logging.basicConfig(level=logging.INFO)
# CARA_VOICE_LOG_LEVEL=DEBUG traces every voice lifecycle event.
logging.getLogger("voice").setLevel(os.environ.get("CARA_VOICE_LOG_LEVEL", "INFO"))


async def main() -> None:
    session = await VoiceSessionFactory.from_yaml()
    async with session:
        await session.run()


if __name__ == "__main__":
    asyncio.run(main())
