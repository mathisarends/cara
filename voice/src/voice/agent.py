import logging

from agent.events import SessionEnded, SessionStarted
from voice.audio import AudioHub, AudioInput, AudioOutput, PlaybackCoordinator
from voice.audio.input import MicrophoneAudioInput
from voice.audio.output import LocalAudioOutput
from voice.audio.session import PortAudioSession
from voice.echo_cancellation import wrap_with_echo_cancellation
from voice.events.bus import EventBus
from voice.events.listener import EarconPlayer, SoundListener
from voice.handler import FollowUpHandler, InterruptionHandler, WakeWordHandler
from voice.llm import ChatModel
from voice.pipeline import TurnController
from voice.stt import CartesiaSpeechToText, SpeechToText
from voice.tts import CartesiaTextToSpeech, RawOutputFormat, TextToSpeech
from voice.wakeword import WakeWord, WakeWordListener, WakeWordSource

logger = logging.getLogger(__name__)

_DEFAULT_CARTESIA_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"


class VoiceAgent:
    """Owns and wires one wake-word-driven voice session."""

    def __init__(
        self,
        *,
        llm: ChatModel,
        event_bus: EventBus | None = None,
        audio_input: AudioInput | None = None,
        audio_output: AudioOutput | None = None,
        wake_word: WakeWordSource | None = None,
        speech_to_text: SpeechToText | None = None,
        text_to_speech: TextToSpeech | None = None,
    ) -> None:
        self._event_bus = event_bus or EventBus()
        self._audio_session = (
            PortAudioSession() if audio_input is None or audio_output is None else None
        )

        physical_input = audio_input or MicrophoneAudioInput(
            session=self._audio_session
        )
        physical_output = audio_output or LocalAudioOutput(session=self._audio_session)
        echo_cancelled_input, echo_referenced_output = wrap_with_echo_cancellation(
            physical_input,
            physical_output,
        )

        self._audio_hub = AudioHub(echo_cancelled_input)
        self._playback = PlaybackCoordinator(echo_referenced_output)
        self._speech_to_text = speech_to_text or CartesiaSpeechToText(
            sample_rate=self._audio_hub.format.sample_rate
        )
        self._text_to_speech = text_to_speech or CartesiaTextToSpeech(
            voice_id=_DEFAULT_CARTESIA_VOICE_ID,
            language="de",
            output_format=RawOutputFormat(sample_rate=24_000),
        )
        self._wake_word = wake_word or WakeWordListener(
            self._audio_hub,
            wake_word=WakeWord.HEY_MYCROFT,
            sensitivity=0.5,
            cooldown=1.5,
        )
        self._setup_handlers(llm)
        self._closed = False
        self._setup_listeners()

    def _setup_handlers(self, llm: ChatModel) -> None:
        self._controller = TurnController(
            audio_hub=self._audio_hub,
            wake_word_phrase=self._wake_word.phrase,
            speech_to_text=self._speech_to_text,
            llm=llm,
            text_to_speech=self._text_to_speech,
            playback=self._playback,
            event_bus=self._event_bus,
        )
        self._interruption_handler = InterruptionHandler(
            event_bus=self._event_bus,
            turns=self._controller,
            playback=self._playback,
        )
        self._wake_word_handler = WakeWordHandler(
            event_bus=self._event_bus,
            source=self._wake_word,
        )
        self._follow_up_handler = FollowUpHandler(event_bus=self._event_bus)

    def _setup_listeners(self) -> None:
        earcons = EarconPlayer(self._playback)
        self._sound_listener = SoundListener(self._event_bus, earcons)

    async def run(self) -> None:
        if self._closed:
            raise RuntimeError("Voice agent is closed.")

        logger.info('Listening for "Hey Mycroft". Press Ctrl+C to quit.')
        try:
            await self._event_bus.dispatch(SessionStarted())
            await self._audio_hub.start()
            await self._wake_word_handler.run()
        finally:
            try:
                await self._event_bus.dispatch(SessionEnded())
            finally:
                await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        self._wake_word_handler.close()
        self._follow_up_handler.close()
        await self._playback.interrupt()
        await self._controller.close()
        await self._audio_hub.stop()
        await self._speech_to_text.aclose()
        await self._text_to_speech.aclose()
        await self._playback.stop()
        if self._audio_session is not None:
            self._audio_session.close()
