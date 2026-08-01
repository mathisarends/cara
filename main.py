import asyncio
import logging
from pathlib import Path

from agenttoolkit import Skills
from dotenv import load_dotenv
from llmify import ChatCodex
from transitbus import EventBus

from cara import Agent, SpeechSettings, VoiceSession
from cara.audio import (
    AudioOutput,
    AudioPlayer,
    EarconPlayer,
    LocalAudioSink,
    MicrophoneRecorder,
    MicrophoneStream,
)
from cara.audio.device import PortAudioDevice
from cara.speech import OpenAISpeechToText, OpenAITextToSpeech, SpeechInput, SpeechOutput
from cara.tools import build_tools
from cara.wakeword import WakeWord, WakeWordListener

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

load_dotenv(override=True)


async def main() -> None:
    event_bus = EventBus()
    audio_device = PortAudioDevice()
    microphone = MicrophoneStream(device=audio_device)
    audio_player = AudioPlayer(
        LocalAudioSink(device=audio_device),
        active_output=AudioOutput.LOCAL,
    )

    skills = Skills.from_local_dir(Path(__file__).parent / "skills")
    llm = ChatCodex.from_cli(model="gpt-5.6-terra")
    tools = build_tools(audio_player, skills=skills)
    agent = Agent(
        llm=llm,
        tools=tools,
        skills=skills,
    )
    speech_settings = SpeechSettings(language="de")
    voice_session = VoiceSession(
        agent=agent,
        speech_input=SpeechInput(
            MicrophoneRecorder(microphone),
            OpenAISpeechToText(),
            speech_settings,
            event_bus,
        ),
        speech_output=SpeechOutput(
            OpenAITextToSpeech(),
            audio_player,
            speech_settings,
            event_bus,
        ),
        wake_word_listener=WakeWordListener(
            microphone,
            wake_word=WakeWord.HEY_MYCROFT,
            sensitivity=0.5,
        ),
        event_bus=event_bus,
        earcons=EarconPlayer(audio_player),
    )

    try:
        await voice_session.run()
    finally:
        microphone.close()
        audio_device.close()


if __name__ == "__main__":
    asyncio.run(main())
