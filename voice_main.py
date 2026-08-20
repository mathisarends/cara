import asyncio
import logging
from pathlib import Path

from agenttoolkit import Skills
from dotenv import load_dotenv
from sonosify import SonosClient

from agent import Agent, ModelSwitch
from agent.sandbox import SandboxDefinition
from agent.tools import build_tools
from llm import CodexModel, CodexReasoningEffort, create_codex_model
from voice import (
    HueObserver,
    SonosAudioFocusObserver,
    SonosDuckingPolicy,
    SoundObserver,
    SpeechBargeIn,
    VoiceAgent,
)
from voice.audio.output.sonos import SonosOutput
from voice.sonos import SonosSettings
from voice.tts import DeepgramTextToSpeech, DeepgramVoice

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("voice.wakeword.listener").setLevel(logging.DEBUG)

load_dotenv(override=True)

_SKILLS_ROOT = Path(__file__).parent / "skills"
_SANDBOX_CONFIG = Path(__file__).parent / "sandbox.yml"


async def main() -> None:
    skills = Skills.from_dir(_SKILLS_ROOT)
    sonos_settings = SonosSettings()
    async with SonosClient(sonos_settings.ip_address) as sonos_client:
        audio_output = SonosOutput(client=sonos_client, settings=sonos_settings)
        models = ModelSwitch(
            {
                CodexModel.SPARK.value: create_codex_model(
                    CodexModel.SPARK,
                    reasoning_effort=CodexReasoningEffort.LOW,
                ),
                CodexModel.GPT_5_5.value: create_codex_model(CodexModel.GPT_5_5),
                CodexModel.GPT_5_4.value: create_codex_model(CodexModel.GPT_5_4),
            },
            default=CodexModel.SPARK.value,
        )
        tools = build_tools(
            injected_dependencies=(audio_output, models),
            skills=skills,
            sandbox=SandboxDefinition.from_yaml(_SANDBOX_CONFIG),
        )
        agent_session = Agent(
            models=models,
            tools=tools,
            skills=skills,
        )
        agent = VoiceAgent(
            agent_session=agent_session,
            audio_output=audio_output,
            text_to_speech=DeepgramTextToSpeech(voice=DeepgramVoice.AURA_2_ATHENA_EN),
            barge_in=SpeechBargeIn(),
            observers=(
                SoundObserver(),
                HueObserver(),
                SonosAudioFocusObserver(policy=SonosDuckingPolicy(client=sonos_client)),
            ),
        )
        await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
