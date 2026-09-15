import asyncio
import logging

from dotenv import load_dotenv
from sonosify import SonosClient

from voice import (
    GatewayVoiceSession,
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
from voice.sonos import SonosSettings

logging.basicConfig(level=logging.INFO)
load_dotenv()


async def main() -> None:
    sonos_settings = SonosSettings()
    config = VoiceChannelConfig.from_yaml()
    gateway_session = await GatewayVoiceSession.connect(
        config.gateway.url,
        token=config.gateway.token,
        device_id=config.voice.device_id,
        channel=config.voice.channel,
        new_session=config.voice.new_session,
        inactivity_timeout_seconds=config.voice.inactivity_timeout_seconds,
    )
    async with gateway_session, SonosClient(sonos_settings.ip_address) as sonos_client:
        audio_output = SonosOutput(client=sonos_client, settings=sonos_settings)
        voice_channel = VoiceChannel(
            gateway_session=gateway_session,
            audio_output=audio_output,
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
