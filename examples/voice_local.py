import asyncio
import logging

from dotenv import load_dotenv

from voice import (
    GatewayVoiceSession,
    HueObserver,
    SoundObserver,
    SpeechBargeIn,
    VoiceChannel,
    VoiceChannelConfig,
    WakeWord,
    WakeWordSettings,
)

logging.basicConfig(level=logging.INFO)
load_dotenv()


async def main() -> None:
    config = VoiceChannelConfig.from_yaml()
    gateway_session = await GatewayVoiceSession.connect(
        config.gateway.url,
        token=config.gateway.token,
        device_id=config.voice.device_id,
        channel=config.voice.channel,
        new_session=config.voice.new_session,
        inactivity_timeout_seconds=config.voice.inactivity_timeout_seconds,
    )
    async with gateway_session:
        voice_channel = VoiceChannel(
            gateway_session=gateway_session,
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
