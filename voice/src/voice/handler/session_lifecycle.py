from agent.events import SessionStarted
from voice.audio import AudioHub, PlaybackCoordinator, PortAudioSession
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing
from voice.stt import SpeechToText
from voice.tts import TextToSpeech


class SessionLifecycleHandler:
    """Starts capture and releases the resources owned by a voice session."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        audio_hub: AudioHub,
        playback: PlaybackCoordinator,
        speech_to_text: SpeechToText,
        text_to_speech: TextToSpeech,
        audio_session: PortAudioSession | None,
    ) -> None:
        self._audio_hub = audio_hub
        self._playback = playback
        self._speech_to_text = speech_to_text
        self._text_to_speech = text_to_speech
        self._audio_session = audio_session

        event_bus.on(SessionStarted, self._on_session_started)
        event_bus.on(VoiceResourcesClosing, self._close_audio)
        event_bus.on(VoiceResourcesClosing, self._close_speech_to_text)
        event_bus.on(VoiceResourcesClosing, self._close_text_to_speech)

    async def _on_session_started(self, _: SessionStarted) -> None:
        await self._audio_hub.start()

    async def _close_audio(self, _: VoiceResourcesClosing) -> None:
        await self._playback.interrupt()
        await self._audio_hub.stop()
        await self._playback.stop()
        if self._audio_session is not None:
            self._audio_session.close()

    async def _close_speech_to_text(self, _: VoiceResourcesClosing) -> None:
        await self._speech_to_text.aclose()

    async def _close_text_to_speech(self, _: VoiceResourcesClosing) -> None:
        await self._text_to_speech.aclose()
