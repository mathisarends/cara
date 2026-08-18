import asyncio
import contextlib
import logging

from dotenv import load_dotenv

from voice import VoiceAgent
from voice.llm import EchoAgentSession
from voice.tts.cartesia import CartesiaTextToSpeech

load_dotenv(override=True)


async def main() -> None:
    echo_agent = EchoAgentSession(prefix="You said: ")
    tts = CartesiaTextToSpeech(language="en")

    agent = VoiceAgent(agent_session=echo_agent, text_to_speech=tts)
    await agent.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with contextlib.suppress(KeyboardInterrupt, EOFError):
        asyncio.run(main())
