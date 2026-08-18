import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sonosify import SonosController

from voice import SpeechBargeIn, VoiceAgent
from voice.audio.output.sonos import SonosOutput, SonosSettings
from voice.llm import EchoAgentSession
from voice.tts.cartesia import CartesiaTextToSpeech

logging.basicConfig(level=logging.INFO)

load_dotenv(override=True)


@contextlib.asynccontextmanager
async def _create_sonos_output() -> AsyncGenerator[SonosOutput]:
    settings = SonosSettings()
    controller = SonosController()
    client = await controller.client(
        settings.speaker_name,
        ip=settings.ip_address,
    )
    async with client:
        yield SonosOutput(client=client, settings=settings)


async def main() -> None:
    agent_session = EchoAgentSession()
    tts = CartesiaTextToSpeech(language="en")
    async with _create_sonos_output() as audio_output:
        agent = VoiceAgent(
            agent_session=agent_session,
            audio_output=audio_output,
            text_to_speech=tts,
            barge_in=SpeechBargeIn(),
        )
        await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
