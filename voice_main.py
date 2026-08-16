import asyncio
import contextlib
import logging

from dotenv import load_dotenv

from voice import VoiceAgent
from voice.llm import EchoLanguageModel


async def main() -> None:
    load_dotenv(override=True)
    await VoiceAgent(llm=EchoLanguageModel()).run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with contextlib.suppress(KeyboardInterrupt, EOFError):
        asyncio.run(main())
