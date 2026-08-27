import asyncio
import logging
import os

from dotenv import load_dotenv
from sonosify import SonosClient

from voice import (
    HueObserver,
    SonosAudioFocusObserver,
    SonosDuckingPolicy,
    SoundObserver,
    SpeechBargeIn,
    VoiceChannel,
    WakeWord,
    WakeWordSettings,
)
from voice.audio.output.sonos import SonosOutput
from voice.llm import GatewayAgentSession
from voice.sonos import SonosSettings
from voice.tts import DeepgramTextToSpeech, DeepgramVoice

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("voice.wakeword.listener").setLevel(logging.DEBUG)

load_dotenv(override=True)

_GATEWAY_URL = os.environ.get(
    "CARA_GATEWAY_URL",
    "ws://127.0.0.1:8000/v1/gateway",
)
_GATEWAY_TOKEN = os.environ["CARA_GATEWAY_TOKEN"]
_VOICE_CHANNEL = os.environ.get("CARA_VOICE_CHANNEL", "voice")
_VOICE_ACCOUNT_ID = os.environ.get("CARA_VOICE_ACCOUNT_ID")
_NEW_VOICE_SESSION = os.environ.get("CARA_VOICE_NEW_SESSION", "false").lower() in {
    "1",
    "true",
    "yes",
}


async def main() -> None:
    sonos_settings = SonosSettings()
    gateway_session = await GatewayAgentSession.connect(
        _GATEWAY_URL,
        token=_GATEWAY_TOKEN,
        channel=_VOICE_CHANNEL,
        account_id=_VOICE_ACCOUNT_ID,
        new_session=_NEW_VOICE_SESSION,
    )
    async with gateway_session, SonosClient(sonos_settings.ip_address) as sonos_client:
        audio_output = SonosOutput(client=sonos_client, settings=sonos_settings)
        voice_channel = VoiceChannel(
            agent_session=gateway_session,
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
