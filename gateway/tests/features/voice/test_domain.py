from uuid import uuid4

import pytest

from gateway.features.voice.domain import (
    Activation,
    AudioEncoding,
    AudioFormat,
    InvalidVoiceTurnTransitionError,
    VoiceSession,
    VoiceTurnStatus,
)


def test_voice_turn_lifecycle() -> None:
    audio_input = AudioFormat(AudioEncoding.PCM_S16LE, 16_000, 1)
    audio_output = AudioFormat(AudioEncoding.PCM_S16LE, 24_000, 1)
    voice_session = VoiceSession(
        uuid4(),
        "kitchen",
        audio_input,
        audio_output,
    )

    turn = voice_session.start_turn(Activation.WAKE_WORD)
    turn.end_input()
    user_message_id = uuid4()
    turn.transcribe("  wie   spät ist es? ", user_message_id)
    turn.start_speaking()
    turn.complete()

    assert turn.status is VoiceTurnStatus.COMPLETED
    assert turn.transcript == "wie spät ist es?"
    assert turn.user_message_id == user_message_id
    assert voice_session.active_turn is None


def test_terminal_turn_cannot_transition_again() -> None:
    audio_input = AudioFormat(AudioEncoding.PCM_S16LE, 16_000, 1)
    audio_output = AudioFormat(AudioEncoding.PCM_S16LE, 24_000, 1)
    voice_session = VoiceSession(uuid4(), "desk", audio_input, audio_output)
    turn = voice_session.start_turn(Activation.MANUAL)
    turn.discard()

    with pytest.raises(InvalidVoiceTurnTransitionError):
        turn.cancel()
