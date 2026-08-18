import asyncio
import logging

from dotenv import load_dotenv

from voice import SpeechBargeIn, VoiceAgent
from voice.audio.output.sonos import SonosOutput
from voice.llm import CodexAgentSession
from voice.tts.cartesia import CartesiaTextToSpeech

logging.basicConfig(level=logging.INFO)
logging.getLogger("voice.wakeword.listener").setLevel(logging.DEBUG)

load_dotenv(override=True)


async def main() -> None:
    agent_session = CodexAgentSession()
    tts = CartesiaTextToSpeech(language="en")
    agent = VoiceAgent(
        agent_session=agent_session,
        audio_output=SonosOutput(),
        text_to_speech=tts,
        barge_in=SpeechBargeIn(),
    )
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
