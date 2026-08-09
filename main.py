import argparse
import asyncio
import logging
from pathlib import Path

from agenttoolkit import Skills
from agenttoolkit.builtins import BindMount, LocalWorkspace
from dotenv import load_dotenv
from llmify import ChatModel
from transitbus import EventBus

from cara import (
    Agent,
    HueListener,
    SpeechInput,
    SpeechOutput,
    SpeechSettings,
    TerminalSession,
    VoiceSession,
)
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
from llm import CodexModel, create_codex_model

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

load_dotenv(override=True)

_PROJECT_ROOT = Path(__file__).parent
_WORKSPACE_ROOT = _PROJECT_ROOT / "workspace"
_SKILLS_ROOT = _PROJECT_ROOT / "skills"
_CARA_SRC = _PROJECT_ROOT / "cara" / "src" / "cara"
_CARA_EXAMPLES = _PROJECT_ROOT / "cara" / "examples"


async def main(mode: str = "voice") -> None:
    skills = Skills.from_local_dir(_SKILLS_ROOT)
    llm = create_codex_model(CodexModel.TERRA)
    event_bus = EventBus()
    hue_listener = HueListener(event_bus)
    try:
        if mode == "terminal":
            await TerminalSession(
                _build_agent(llm, skills, event_bus=event_bus),
                event_bus=event_bus,
            ).run()
            return
        if mode == "voice":
            await _run_voice(llm, skills, event_bus)
            return
        raise ValueError(f"Unknown session mode: {mode!r}")
    finally:
        await hue_listener.close()


async def _run_voice(llm: ChatModel, skills: Skills, event_bus: EventBus) -> None:
    audio_device = PortAudioDevice()
    microphone = MicrophoneStream(device=audio_device)
    audio_player = AudioPlayer(
        LocalAudioSink(device=audio_device),
        active_output=AudioOutput.LOCAL,
    )

    agent = _build_agent(llm, skills, audio_player, event_bus=event_bus)
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


def _build_agent(
    llm: ChatModel,
    skills: Skills,
    *tool_dependencies: object,
    event_bus: EventBus | None = None,
) -> Agent:
    return Agent(
        llm=llm,
        tools=build_tools(
            *tool_dependencies,
            skills=skills,
            workspace=_create_workspace(),
            sandbox_mounts=_editable_sandbox_mounts(),
        ),
        prompt_root=_WORKSPACE_ROOT,
        skills=skills,
        event_bus=event_bus,
    )


def _create_workspace() -> LocalWorkspace:
    return LocalWorkspace(
        _WORKSPACE_ROOT,
        mounts={
            "/src/cara": _CARA_SRC,
            "/experiments": _CARA_EXAMPLES,
            "/skills": _SKILLS_ROOT,
        },
        max_file_bytes=1_000_000,
    )


def _editable_sandbox_mounts() -> tuple[BindMount, ...]:
    return (
        BindMount.read_write(_CARA_SRC, "/src/cara"),
        BindMount.read_write(_CARA_EXAMPLES, "/experiments"),
        BindMount.read_write(_SKILLS_ROOT, "/skills"),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Cara through voice or terminal input."
    )
    parser.add_argument(
        "--mode",
        choices=("voice", "terminal"),
        default="voice",
        help="Input and output channel to use (default: voice).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args().mode))
