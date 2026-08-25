"""Voice agent activated by a timer as well as by the wake word.

The timer stands in for any out-of-band trigger — a hardware button, a hotkey,
or a gateway push once the session can receive server-initiated turns. It shows
both activation kinds:

- `activate()` opens the microphone and waits for the user, like a wake word.
- `prompt(text)` hands the agent text directly, skipping speech-to-text
  entirely; the agent performs it and speaks the answer, and the usual
  follow-up window afterwards lets the user reply without a wake word.

An activation that arrives while a turn is already running is dropped, so a
timer tick during a conversation is simply lost for now.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv

from voice import ExternalActivationSource, VoiceAgent
from voice.llm import GatewayAgentSession

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

load_dotenv(override=True)

logger = logging.getLogger(__name__)

_GATEWAY_URL = os.environ.get(
    "CARA_GATEWAY_URL",
    "ws://127.0.0.1:8000/v1/gateway",
)
_GATEWAY_TOKEN = os.environ["CARA_GATEWAY_TOKEN"]
_INTERVAL_SECONDS = float(os.environ.get("CARA_VOICE_ACTIVATION_INTERVAL", "30"))
_HEARTBEAT_PROMPT = (
    "This is a heartbeat turn. Briefly tell the user what time it is "
    "and whether anything needs their attention."
)
# An unattended activation should give up quickly when nobody answers, rather
# than hold the turn open for the wake word's far longer default.
_LISTEN_SECONDS = 5.0


async def main() -> None:
    activation = ExternalActivationSource()
    gateway_session = await GatewayAgentSession.connect(
        _GATEWAY_URL,
        token=_GATEWAY_TOKEN,
    )
    async with gateway_session:
        agent = VoiceAgent(
            agent_session=gateway_session,
            activation_sources=(activation,),
        )
        heartbeat = asyncio.create_task(
            _trigger_periodically(activation),
            name="example-heartbeat",
        )
        try:
            await agent.start()
        finally:
            heartbeat.cancel()


async def _trigger_periodically(activation: ExternalActivationSource) -> None:
    while True:
        await asyncio.sleep(_INTERVAL_SECONDS)
        logger.info("Heartbeat: running a turn on a prompt, without listening first")
        await activation.prompt(_HEARTBEAT_PROMPT)

        await asyncio.sleep(_INTERVAL_SECONDS)
        logger.info("Button: opening the microphone without a wake word")
        await activation.activate(speech_start_timeout=_LISTEN_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
