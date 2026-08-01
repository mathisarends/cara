import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv
from llmify import ChatOpenAI
from transitbus import EventBus

from cara import SpeechSettings, VoiceAgent
from cara.audio import AudioOutput, AudioPlayer, LocalAudioSink
from cara.file_system import LocalFileSystem, Workspace
from cara.skills import Skills
from cara.wakeword import WakeWord, WakeWordSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

load_dotenv(override=True)


async def main() -> None:
    event_bus = EventBus()
    audio_player = AudioPlayer(
        LocalAudioSink(),
        active_output=AudioOutput.LOCAL,
    )

    skills = Skills.from_directory(LocalFileSystem(Workspace(Path(__file__).parent)), "skills")

    assistant = VoiceAgent(
        llm=ChatOpenAI(model="gpt-5.6-terra", reasoning_effort="none"),
        speech_settings=SpeechSettings(language="de"),
        wake_word_settings=WakeWordSettings(wake_word=WakeWord.HEY_MYCROFT, sensitivity=0.5),
        event_bus=event_bus,
        player=audio_player,
        skills=skills,
    )

    await assistant.start()


if __name__ == "__main__":
    asyncio.run(main())
