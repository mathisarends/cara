from typing import cast
from uuid import uuid4

import pytest
from obstore.store import MemoryStore

from gateway.features.voice.application import (
    AudioEncoder,
    VoiceRecordingService,
    VoiceRecordingStore,
    VoiceSessionService,
)
from gateway.features.voice.domain import (
    Activation,
    AudioEncoding,
    AudioFormat,
    VoiceRecordingNotFoundError,
    VoiceSession,
)
from gateway.features.voice.infrastructure.lame_encoder import LameMp3Encoder
from gateway.features.voice.infrastructure.recording_store import (
    ObjectStorageVoiceRecordingStore,
)
from gateway.platform.storage.obstore_storage import ObstoreObjectStorage


async def test_finished_turns_are_saved_with_input_before_output() -> None:
    voice_session = _voice_session()
    store = _RecordingStore()
    recordings = _recordings(voice_session, store)
    completed = voice_session.start_turn(Activation.WAKE_WORD)
    recordings.record_input(completed.id, b"hi")
    recordings.record_output(completed.id, b"hello")
    completed.end_input()
    completed.transcribe("hi", uuid4())
    completed.start_speaking()
    completed.complete()
    discarded = voice_session.start_turn(Activation.FOLLOW_UP)
    recordings.record_input(discarded.id, b"noise")
    discarded.discard()
    active = voice_session.start_turn(Activation.WAKE_WORD)
    recordings.record_input(active.id, b"still talking")

    recordings.finish(voice_session)
    await recordings.close()

    assert store.turns == {(voice_session.id, 1): b"16000:hi24000:hello"}


async def test_missing_recording_is_reported() -> None:
    voice_session = _voice_session()
    recordings = _recordings(voice_session, _RecordingStore())

    with pytest.raises(VoiceRecordingNotFoundError):
        await recordings.get(voice_session.id)


async def test_object_storage_joins_turns_in_turn_order() -> None:
    store = ObjectStorageVoiceRecordingStore(ObstoreObjectStorage(MemoryStore()))
    voice_session_id = uuid4()
    await store.save_turn(voice_session_id, 10, b"third")
    await store.save_turn(voice_session_id, 2, b"second")
    await store.save_turn(voice_session_id, 1, b"first")
    await store.save_turn(uuid4(), 1, b"other session")

    assert await store.load(voice_session_id) == b"firstsecondthird"
    assert await store.load(uuid4()) is None


async def test_lame_encoder_resamples_every_input_to_one_mp3_stream() -> None:
    encoder = LameMp3Encoder(output_sample_rate=24_000, bit_rate_kbps=64)

    user = await encoder.encode(b"\x00\x00" * 16_000, 16_000)
    assistant = await encoder.encode(b"\x00\x00" * 24_000, 24_000)

    # MPEG-2 Layer III frame sync; 24 kHz output is MPEG-2 for both inputs.
    assert user[:2] == assistant[:2] == b"\xff\xf3"


def _voice_session() -> VoiceSession:
    return VoiceSession(
        uuid4(),
        "kitchen",
        AudioFormat(AudioEncoding.PCM_S16LE, 16_000, 1),
        AudioFormat(AudioEncoding.PCM_S16LE, 24_000, 1),
    )


def _recordings(
    voice_session: VoiceSession,
    store: "_RecordingStore",
) -> VoiceRecordingService:
    return VoiceRecordingService(
        cast(VoiceSessionService, _VoiceSessions(voice_session)),
        cast(AudioEncoder, _TaggingEncoder()),
        cast(VoiceRecordingStore, store),
    )


class _VoiceSessions:
    def __init__(self, voice_session: VoiceSession) -> None:
        self._voice_session = voice_session

    async def get(self, voice_session_id):
        assert voice_session_id == self._voice_session.id
        return self._voice_session


class _TaggingEncoder:
    async def encode(self, pcm: bytes, sample_rate: int) -> bytes:
        return f"{sample_rate}:".encode() + pcm


class _RecordingStore:
    def __init__(self) -> None:
        self.turns: dict[tuple[object, int], bytes] = {}

    async def save_turn(self, voice_session_id, voice_turn_index, audio) -> None:
        self.turns[(voice_session_id, voice_turn_index)] = audio

    async def load(self, voice_session_id) -> bytes | None:
        return None
