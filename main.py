import asyncio
import logging

from cara import (
    AssistantConfig,
    VoiceAssistant,
)
from cara.wakeword import WakeWord, WakeWordListener

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main() -> None:
    assistant = VoiceAssistant(config=AssistantConfig(language="de"))

    async def on_wake_word() -> None:
        await assistant.handle_wake_word()

    listener = WakeWordListener(
        on_detection=on_wake_word,
        wake_word=WakeWord.HEY_MYCROFT,
        sensitivity=0.5,
    )
    await listener.listen()


if __name__ == "__main__":
    asyncio.run(main())
