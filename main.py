import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from cara import SpeechSettings, VoiceAssistant
from cara.audio import AudioOutput, AudioPlayer, WavAudioPlayer
from cara.audio.sonos import SonosAudioPlayer
from cara.events import EventBus
from cara.file_system import LocalFileSystem, Workspace
from cara.listener import HueListener
from cara.skills import Skills
from cara.wakeword import WakeWord, WakeWordSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

load_dotenv(override=True)


async def main() -> None:
    event_bus = EventBus()
    audio_player = AudioPlayer(
        WavAudioPlayer(),
        SonosAudioPlayer(),
        active_output=AudioOutput.SONOS,
    )

    skills = Skills.from_directory(LocalFileSystem(Workspace(Path(__file__).parent)), "skills")

    assistant = VoiceAssistant(
        speech_settings=SpeechSettings(language="de"),
        wake_word_settings=WakeWordSettings(wake_word=WakeWord.HEY_MYCROFT, sensitivity=0.5),
        event_bus=event_bus,
        player=audio_player,
        skills=skills,
    )

    HueListener(event_bus=event_bus, room_name="Mein Zimmer")

    await assistant.start()


if __name__ == "__main__":
    asyncio.run(main())
