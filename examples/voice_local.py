import asyncio
import logging

from dotenv import load_dotenv

from voice import (
    HueObserver,
    SoundObserver,
    SpeechBargeIn,
    VoiceChannel,
    VoiceChannelConfig,
    WakeWord,
    WakeWordSettings,
)
from voice.llm import GatewayAgentSession
from voice.tts import DeepgramTextToSpeech, DeepgramVoice

logging.basicConfig(level=logging.INFO)
load_dotenv()


async def main() -> None:
    config = VoiceChannelConfig.from_yaml()
    gateway_session = await GatewayAgentSession.connect(
        config.gateway.url,
        token=config.gateway.token,
        channel=config.voice.channel,
        account_id=config.voice.account_id,
        new_session=config.voice.new_session,
    )
    async with gateway_session:
        voice_channel = VoiceChannel(
            agent_session=gateway_session,
            activation_sources=(gateway_session,),
            text_to_speech=DeepgramTextToSpeech(voice=DeepgramVoice.AURA_2_ATHENA_EN),
            barge_in=SpeechBargeIn(),
            wake_word_settings=WakeWordSettings(wake_word=WakeWord.HEY_JARVIS),
            observers=(
                SoundObserver(),
                HueObserver(),
            ),
        )
        await voice_channel.start()


if __name__ == "__main__":
    asyncio.run(main())
