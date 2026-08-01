import asyncio
import logging
from pathlib import Path

from agenttoolkit import Skills
from dotenv import load_dotenv
from llmify import ChatCodex
from transitbus import EventBus

from cara import Agent, SpeechSettings, VoiceSession
from cara.audio import AudioPlayer, EarconPlayer, LocalAudioSink, MicrophoneRecorder, MicrophoneStream
from cara.audio.device import PortAudioDevice
from cara.speech import OpenAISpeechToText, OpenAITextToSpeech, SpeechInput, SpeechOutput
from cara.tools import build_tools
from cara.wakeword import WakeWord, WakeWordListener

PROJECT_ROOT = Path(__file__).resolve().parents[1]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    event_bus = EventBus()
    audio_device = PortAudioDevice()
    microphone = MicrophoneStream(device=audio_device)
    player = AudioPlayer(LocalAudioSink(device=audio_device))
    speech_settings = SpeechSettings(language="de")
    skills = Skills.from_local_dir(PROJECT_ROOT / "skills")
    agent = Agent(
        llm=ChatCodex.from_cli(model="gpt-5.6-terra"),
        tools=build_tools(player, skills=skills),
        skills=skills,
    )
    session = VoiceSession(
        agent=agent,
        speech_input=SpeechInput(
            MicrophoneRecorder(microphone),
            OpenAISpeechToText(),
            speech_settings,
            event_bus,
        ),
        speech_output=SpeechOutput(
            OpenAITextToSpeech(),
            player,
            speech_settings,
            event_bus,
        ),
        wake_word_listener=WakeWordListener(
            microphone,
            wake_word=WakeWord.HEY_MYCROFT,
            sensitivity=0.5,
        ),
        event_bus=event_bus,
        earcons=EarconPlayer(player),
    )

    try:
        await session.run()
    finally:
        microphone.close()
        audio_device.close()


if __name__ == "__main__":
    asyncio.run(main())
