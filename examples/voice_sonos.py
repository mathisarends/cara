import asyncio
import logging

from dotenv import load_dotenv
from sonosify import SonosClient

from voice import (
    HueObserver,
    SonosAudioFocusObserver,
    SonosDuckingPolicy,
    SoundObserver,
    SpeechBargeIn,
    VoiceChannel,
    VoiceChannelConfig,
    WakeWord,
    WakeWordSettings,
)
from voice.audio.output.sonos import SonosOutput
from voice.llm import GatewayAgentSession
from voice.sonos import SonosSettings
from voice.tts import DeepgramTextToSpeech, DeepgramVoice

logging.basicConfig(level=logging.INFO)
load_dotenv()


async def main() -> None:
    sonos_settings = SonosSettings()
    config = VoiceChannelConfig.from_yaml()
    gateway_session = await GatewayAgentSession.connect(
        config.gateway.url,
        token=config.gateway.token,
        channel=config.voice.channel,
        new_session=config.voice.new_session,
    )
    async with gateway_session, SonosClient(sonos_settings.ip_address) as sonos_client:
        audio_output = SonosOutput(client=sonos_client, settings=sonos_settings)
        voice_channel = VoiceChannel(
            agent_session=gateway_session,
            activation_sources=(gateway_session,),
            audio_output=audio_output,
            text_to_speech=DeepgramTextToSpeech(voice=DeepgramVoice.AURA_2_ATHENA_EN),
            barge_in=SpeechBargeIn(),
            wake_word_settings=WakeWordSettings(wake_word=WakeWord.HEY_JARVIS),
            observers=(
                SoundObserver(),
                HueObserver(),
                SonosAudioFocusObserver(policy=SonosDuckingPolicy(client=sonos_client)),
            ),
        )
        await voice_channel.start()


if __name__ == "__main__":
    asyncio.run(main())
