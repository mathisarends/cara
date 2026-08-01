import asyncio
import logging
from pathlib import Path

from agenttoolkit import Skills
from dotenv import load_dotenv
from llmify import ChatCodex
from transitbus import EventBus

from cara import SpeechSettings, VoiceAgent
from cara.audio import AudioOutput, AudioPlayer, LocalAudioSink
from cara.wakeword import WakeWord, WakeWordSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

load_dotenv(override=True)


async def main() -> None:
    event_bus = EventBus()
    audio_player = AudioPlayer(
        LocalAudioSink(),
        active_output=AudioOutput.LOCAL,
    )

    skills = Skills.from_local_dir(Path(__file__).parent / "skills")
    llm = ChatCodex.from_cli(model="gpt-5.6-terra")

    assistant = VoiceAgent(
        llm=llm,
        speech_settings=SpeechSettings(language="de"),
        wake_word_settings=WakeWordSettings(wake_word=WakeWord.HEY_MYCROFT, sensitivity=0.5),
        event_bus=event_bus,
        player=audio_player,
        skills=skills,
    )

    await assistant.start()


if __name__ == "__main__":
    asyncio.run(main())
