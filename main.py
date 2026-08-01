import argparse
import asyncio
import logging
from pathlib import Path

from agenttoolkit import Skills
from dotenv import load_dotenv
from llmify import ChatCodex, ChatModel
from transitbus import EventBus

from cara import Agent, SpeechInput, SpeechOutput, SpeechSettings, TerminalSession, VoiceSession
from cara.audio import (
    AudioOutput,
    AudioPlayer,
    EarconPlayer,
    LocalAudioSink,
    MicrophoneRecorder,
    MicrophoneStream,
)
from cara.audio.device import PortAudioDevice
from cara.speech import OpenAISpeechToText, OpenAITextToSpeech
from cara.tools import build_tools
from cara.wakeword import WakeWord, WakeWordListener

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

load_dotenv(override=True)


async def main(mode: str = "voice") -> None:
    skills = Skills.from_local_dir(Path(__file__).parent / "skills")
    llm = ChatCodex.from_cli(model="gpt-5.6-terra")
    if mode == "terminal":
        await TerminalSession(_build_agent(llm, skills)).run()
        return
    if mode == "voice":
        await _run_voice(llm, skills)
        return
    raise ValueError(f"Unknown session mode: {mode!r}")


async def _run_voice(llm: ChatModel, skills: Skills) -> None:
    event_bus = EventBus()
    audio_device = PortAudioDevice()
    microphone = MicrophoneStream(device=audio_device)
    audio_player = AudioPlayer(
        LocalAudioSink(device=audio_device),
        active_output=AudioOutput.LOCAL,
    )

    agent = _build_agent(llm, skills, audio_player)
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


def _build_agent(llm: ChatModel, skills: Skills, *tool_dependencies: object) -> Agent:
    return Agent(
        llm=llm,
        tools=build_tools(*tool_dependencies, skills=skills),
        skills=skills,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Cara through voice or terminal input.")
    parser.add_argument(
        "--mode",
        choices=("voice", "terminal"),
        default="voice",
        help="Input and output channel to use (default: voice).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args().mode))
