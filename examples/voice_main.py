import asyncio
import logging

from dotenv import load_dotenv
from sonosify import SonosClient

from voice import (
    HueObserver,
    SonosAudioFocusObserver,
    SonosDuckingPolicy,
    SoundObserver,
    VoiceChannel,
    VoiceChannelConfig,
)
from voice.audio.output.sonos import SonosOutput
from voice.config import (
    build_barge_in,
    build_speech_to_text,
    build_text_to_speech,
)
from voice.llm import GatewayAgentSession
from voice.sonos import SonosSettings

logging.basicConfig(level=logging.INFO)
load_dotenv()


async def main() -> None:
    sonos_settings = SonosSettings()
    config = VoiceChannelConfig.from_yaml()
    gateway_session = await GatewayAgentSession.connect(
        config.gateway.url,
        token=config.gateway.token,
        channel=config.voice.channel,
        account_id=config.voice.account_id,
        new_session=config.voice.new_session,
    )
    async with gateway_session, SonosClient(sonos_settings.ip_address) as sonos_client:
        audio_output = SonosOutput(client=sonos_client, settings=sonos_settings)
        voice_channel = VoiceChannel(
            agent_session=gateway_session,
            activation_sources=(gateway_session,),
            audio_output=audio_output,
            text_to_speech=build_text_to_speech(config.text_to_speech),
            speech_to_text=build_speech_to_text(config.speech_to_text),
            barge_in=build_barge_in(config.barge_in),
            wake_word_settings=config.wake_word,
            observers=(
                SoundObserver(),
                HueObserver(),
                SonosAudioFocusObserver(policy=SonosDuckingPolicy(client=sonos_client)),
            ),
        )
        await voice_channel.start()


if __name__ == "__main__":
    asyncio.run(main())
