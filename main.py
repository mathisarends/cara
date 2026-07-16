import asyncio
import logging

from dotenv import load_dotenv

from cara import SpeechSettings, VoiceAssistant
from cara.listener import ConsoleListener
from cara.wakeword import WakeWord, WakeWordSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

load_dotenv(override=True)


async def main() -> None:
    assistant = VoiceAssistant(
        speech_settings=SpeechSettings(language="de"),
        wake_word_settings=WakeWordSettings(wake_word=WakeWord.HEY_MYCROFT, sensitivity=0.5),
    )

    ConsoleListener(assistant.event_bus)
    # HueListener(assistant.event_bus, room_name="Mein Zimmer")

    await assistant.start()


if __name__ == "__main__":
    asyncio.run(main())
