import asyncio
import contextlib
import logging

from dotenv import load_dotenv
from transitbus import EventBus

from agent.events import SessionEnded, SessionStarted
from voice.audio import AudioHub, PlaybackCoordinator
from voice.audio.device import PortAudioDevice
from voice.audio.input import MicrophoneAudioInput
from voice.audio.output import LocalAudioOutput
from voice.echo_cancellation import EchoCancellation
from voice.events.listener import EarconPlayer, SoundListener
from voice.llm import EchoLanguageModel
from voice.pipeline import TurnController
from voice.stt import CartesiaSpeechToText, SpeechToTextConfig
from voice.tts import CartesiaTextToSpeech, RawOutputFormat, TextToSpeechConfig
from voice.wakeword import WakeWord, WakeWordListener

logger = logging.getLogger(__name__)
_CARTESIA_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"


async def main() -> None:
    load_dotenv(override=True)
    event_bus = EventBus()
    device = PortAudioDevice()
    microphone = MicrophoneAudioInput(device=device)
    physical_output = LocalAudioOutput(device=device)
    audio_input, audio_output = EchoCancellation().wrap(microphone, physical_output)
    audio_hub = AudioHub(audio_input)
    playback = PlaybackCoordinator(audio_output)
    wake_word = WakeWordListener(
        audio_hub,
        wake_word=WakeWord.HEY_MYCROFT,
        sensitivity=0.5,
        cooldown=1.5,
    )
    speech_to_text = CartesiaSpeechToText(
        default_config=SpeechToTextConfig(sample_rate=16_000)
    )
    text_to_speech = CartesiaTextToSpeech(
        default_config=TextToSpeechConfig(
            voice_id=_CARTESIA_VOICE_ID,
            language="de",
            output_format=RawOutputFormat(sample_rate=24_000),
        )
    )
    earcons = EarconPlayer(playback)
    SoundListener(event_bus, earcons)

    controller = TurnController(
        audio_hub=audio_hub,
        wake_word=wake_word,
        speech_to_text=speech_to_text,
        llm=EchoLanguageModel(),
        text_to_speech=text_to_speech,
        playback=playback,
        event_bus=event_bus,
    )
    try:
        logger.info('Listening for "Hey Mycroft". Press Ctrl+C to quit.')
        await event_bus.dispatch(SessionStarted())
        try:
            await controller.run()
        finally:
            await event_bus.dispatch(SessionEnded())
    finally:
        await speech_to_text.aclose()
        await text_to_speech.aclose()
        await playback.stop()
        device.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with contextlib.suppress(KeyboardInterrupt, EOFError):
        asyncio.run(main())
