import asyncio
from uuid import uuid4

from voice.audio import AudioPlayback
from voice.integrations import VoiceIntegrationContext
from voice.integrations.notifier import VoiceIntegrationNotifier
from voice.integrations.sounds.integration import (
    _DEFAULT_SOUNDS_DIR,
    Earcon,
    SoundIntegration,
)
from voice.lifecycle import (
    AssistantTurnStarted,
    VoiceConversationEnded,
    VoiceLifecycleEvent,
    WakeWordDetected,
)


class _RecordingPlayback(AudioPlayback):
    def __init__(self) -> None:
        self.audio: list[bytes] = []

    async def play(self, audio: bytes) -> None:
        self.audio.append(audio)


def _played(event: VoiceLifecycleEvent) -> list[bytes]:
    async def run() -> list[bytes]:
        playback = _RecordingPlayback()
        notifier = VoiceIntegrationNotifier((SoundIntegration(),))
        await notifier.start(VoiceIntegrationContext(audio_player=playback))
        await notifier.on_lifecycle_event(event)
        return playback.audio

    return asyncio.run(run())


def _earcon(earcon: Earcon) -> bytes:
    return (_DEFAULT_SOUNDS_DIR / f"{earcon}.wav").read_bytes()


def test_wake_word_detected_plays_the_wake_earcon() -> None:
    event = WakeWordDetected(score=0.8, sequence=4, name="hey_mycroft")

    assert _played(event) == [_earcon(Earcon.WAKE)]


def test_conversation_ended_plays_the_sleep_earcon() -> None:
    event = VoiceConversationEnded(reason="inactivity_timeout")

    assert _played(event) == [_earcon(Earcon.SLEEP)]


def test_assistant_turn_started_plays_the_success_earcon() -> None:
    assert _played(AssistantTurnStarted(turn_id=uuid4())) == [_earcon(Earcon.SUCCESS)]


def test_session_stop_plays_the_sleep_earcon() -> None:
    async def run() -> list[bytes]:
        playback = _RecordingPlayback()
        notifier = VoiceIntegrationNotifier((SoundIntegration(),))
        await notifier.start(VoiceIntegrationContext(audio_player=playback))
        await notifier.stop()
        return playback.audio

    assert asyncio.run(run()) == [_earcon(Earcon.SLEEP)]
