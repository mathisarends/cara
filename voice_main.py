import asyncio
import logging
from pathlib import Path

from agenttoolkit import Skills
from dotenv import load_dotenv

from agent import Agent
from agent.sandbox import SandboxConfig
from agent.tools import build_tools
from llm import CodexModel, CodexReasoningEffort, create_codex_model
from voice import (
    HueObserver,
    SonosPlaybackObserver,
    SoundObserver,
    SpeechBargeIn,
    VoiceAgent,
)
from voice.audio.output.sonos import SonosOutput
from voice.tts import DeepgramTextToSpeech, DeepgramVoice

logging.basicConfig(level=logging.INFO)
logging.getLogger("voice.wakeword.listener").setLevel(logging.DEBUG)

load_dotenv(override=True)

_SKILLS_ROOT = Path(__file__).parent / "skills"


async def main() -> None:
    skills = Skills.from_dir(_SKILLS_ROOT)
    tools = build_tools(skills=skills, sandbox=SandboxConfig(network_access=True))
    agent_session = Agent(
        llm=create_codex_model(
            CodexModel.SPARK,
            reasoning_effort=CodexReasoningEffort.LOW,
        ),
        tools=tools,
        skills=skills,
    )
    agent = VoiceAgent(
        agent_session=agent_session,
        audio_output=SonosOutput(),
        text_to_speech=DeepgramTextToSpeech(voice=DeepgramVoice.AURA_2_ATHENA_EN),
        barge_in=SpeechBargeIn(),
        observers=(
            SoundObserver(),
            HueObserver(),
            SonosPlaybackObserver(),
        ),
    )
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
