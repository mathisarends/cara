"""Activate the Gateway voice session from a timer or the local wake word.

The timer stands in for an out-of-band trigger such as a hardware button or
hotkey. Activations arriving while a turn is active are ignored.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv

from voice import ExternalActivationSource, GatewayVoiceSession, VoiceChannel

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

load_dotenv(override=True)

logger = logging.getLogger(__name__)

_GATEWAY_URL = os.environ.get("CARA_GATEWAY_URL", "http://127.0.0.1:8000")
_GATEWAY_TOKEN = os.environ["CARA_GATEWAY_TOKEN"]
_INTERVAL_SECONDS = float(os.environ.get("CARA_VOICE_ACTIVATION_INTERVAL", "30"))
_LISTEN_SECONDS = 5.0


async def main() -> None:
    activation = ExternalActivationSource()
    gateway_session = await GatewayVoiceSession.connect(
        _GATEWAY_URL,
        token=_GATEWAY_TOKEN,
        device_id="activation-example",
    )
    async with gateway_session:
        voice_channel = VoiceChannel(
            gateway_session=gateway_session,
            activation_sources=(activation,),
        )
        heartbeat = asyncio.create_task(
            _trigger_periodically(activation),
            name="example-heartbeat",
        )
        try:
            await voice_channel.start()
        finally:
            heartbeat.cancel()


async def _trigger_periodically(activation: ExternalActivationSource) -> None:
    while True:
        await asyncio.sleep(_INTERVAL_SECONDS)
        logger.info("Button: opening the microphone without a wake word")
        await activation.activate(speech_start_timeout=_LISTEN_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
