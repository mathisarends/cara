import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx2
import pytest

from gateway_rest_client import (
    AudioEncoding,
    GatewayRestClient,
    VoiceSessionResponse,
    VoiceSessionSnapshotResponse,
    VoiceSessionStatus,
    VoiceTurnResponse,
    VoiceTurnStatus,
)
from gateway_rest_client import AudioFormat as GatewayAudioFormat
from gateway_rpc_client import GatewayRpcClient, VoiceTurnAlreadyActiveError
from gateway_rpc_client.models import (
    Activation,
    VoiceConversationEnded,
    VoiceEventMessage,
    VoiceSessionClosed,
    VoiceTranscriptFinal,
    VoiceTranscriptPartial,
    VoiceTurnCommandResult,
    VoiceTurnStarted,
)
from voice.activation import ActivationKind
from voice.adapters.gateway.backend import GatewayVoiceBackend
from voice.adapters.gateway.framing import MediaFrame, MediaFrameKind
from voice.adapters.gateway.media import MediaTransport
from voice.audio import AudioFormat, AudioFrame
from voice.backend import (
    ActiveTurn,
    BackendAudioEnd,
    BackendAudioFrame,
    BackendSessionState,
    ConversationEnded,
    SessionClosed,
    StartTurn,
    TranscriptCompleted,
    TranscriptUpdated,
    TurnAlreadyActiveError,
    TurnPhase,
    TurnRef,
    TurnStarted,
)

_VOICE_SESSION_ID = uuid4()
_SESSION_ID = uuid4()
_NOW = datetime.now(UTC)


class _Rest:
    def __init__(self, snapshot: VoiceSessionSnapshotResponse) -> None:
        self.snapshot = snapshot
        self.snapshot_reads = 0
        self.closed: list[UUID] = []

    async def get_voice_session(self, voice_session_id: UUID) -> object:
        assert voice_session_id == _VOICE_SESSION_ID
        self.snapshot_reads += 1
        return self.snapshot

    async def close_voice_session(self, voice_session_id: UUID) -> None:
        self.closed.append(voice_session_id)


class _Turns:
    def __init__(self) -> None:
        self.started: VoiceTurnCommandResult | None = None
        self.start_error: Exception | None = None
        self.start_calls: list[tuple[Activation, int | None]] = []

    async def start(
        self,
        *,
        voice_session_id: UUID,
        activation: Activation,
        pre_roll_sequence: int | None,
    ) -> VoiceTurnCommandResult:
        self.start_calls.append((activation, pre_roll_sequence))
        if self.start_error is not None:
            raise self.start_error
        assert self.started is not None
        return self.started


class _Voice:
    def __init__(self, events: list[VoiceEventMessage]) -> None:
        self._events = events
        self.turn = _Turns()

    async def event(self) -> AsyncIterator[VoiceEventMessage]:
        for event in self._events:
            yield event


class _Subscriptions:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID]] = []

    async def subscribe(self, *, session_id: UUID) -> None:
        self.calls.append(("subscribe", session_id))

    async def unsubscribe(self, *, session_id: UUID) -> None:
        self.calls.append(("unsubscribe", session_id))


class _Rpc:
    def __init__(self, events: list[VoiceEventMessage]) -> None:
        self.voice = _Voice(events)
        self.subscription = _Subscriptions()


class _Media:
    def __init__(self, frames: list[MediaFrame]) -> None:
        self._frames = frames
        self.inputs: list[tuple[int, int]] = []

    async def frames(self) -> AsyncIterator[MediaFrame]:
        for frame in self._frames:
            yield frame

    async def send_input(self, turn_index: int, sequence: int, pcm: bytes) -> None:
        self.inputs.append((turn_index, sequence))


class _Gateway:
    def __init__(
        self,
        snapshot: VoiceSessionSnapshotResponse,
        *,
        events: list[VoiceEventMessage] | None = None,
        frames: list[MediaFrame] | None = None,
    ) -> None:
        self.rest = _Rest(snapshot)
        self.rpc = _Rpc(events or [])
        self.media = _Media(frames or [])
        self.backend = GatewayVoiceBackend(
            rest=cast(GatewayRestClient, self.rest),
            rpc=cast(GatewayRpcClient, self.rpc),
            media=cast(MediaTransport, self.media),
            snapshot=snapshot,
            http=httpx2.AsyncClient(),
            resources=AsyncExitStack(),
        )


def test_reports_the_negotiated_formats_and_the_active_turn() -> None:
    turn = _turn(0, VoiceTurnStatus.SPEAKING)
    backend = _Gateway(_snapshot(turn, active=turn)).backend

    assert backend.input_format == AudioFormat(sample_rate=16_000)
    assert backend.output_format == AudioFormat(sample_rate=24_000)
    assert backend.initial_state == BackendSessionState(
        ActiveTurn(TurnRef(turn.id), TurnPhase.SPEAKING)
    )


def test_a_finished_active_turn_is_not_restored() -> None:
    turn = _turn(0, VoiceTurnStatus.COMPLETED)

    assert _Gateway(_snapshot(turn, active=turn)).backend.initial_state == (
        BackendSessionState()
    )


def test_maps_events_and_drops_foreign_and_already_seen_ones() -> None:
    turn_id = uuid4()
    gateway = _Gateway(
        _snapshot(
            _turn(0, VoiceTurnStatus.LISTENING, turn_id=turn_id), last_sequence=5
        ),
        events=[
            _final(turn_id, sequence=5),
            _final(turn_id, sequence=6, voice_session_id=uuid4()),
            _partial(turn_id),
            _final(turn_id, sequence=6),
            _final(turn_id, sequence=6),
            _closed(sequence=7),
            _final(turn_id, sequence=8),
        ],
    )

    assert _collect(gateway.backend.events()) == [
        TranscriptUpdated(TurnRef(turn_id)),
        TranscriptCompleted(TurnRef(turn_id)),
        SessionClosed(reason="replaced"),
    ]


def test_follows_the_voice_session_into_its_next_conversation() -> None:
    next_session_id = uuid4()
    gateway = _Gateway(_snapshot(), events=[_conversation_ended(sequence=1)])
    gateway.rest.snapshot = _snapshot(session_id=next_session_id)

    assert _collect(gateway.backend.events()) == [ConversationEnded(reason="idle")]
    assert gateway.rpc.subscription.calls == [
        ("subscribe", next_session_id),
        ("unsubscribe", _SESSION_ID),
    ]


def test_learns_the_index_of_a_started_turn_before_yielding_it() -> None:
    turn = _turn(3, VoiceTurnStatus.LISTENING)
    gateway = _Gateway(_snapshot(), events=[_turn_started(turn.id, sequence=1)])
    gateway.rest.snapshot = _snapshot(turn)

    async def run() -> list[object]:
        events = [event async for event in gateway.backend.events()]
        await gateway.backend.send_input(TurnRef(turn.id), AudioFrame(9, b"\x00\x00"))
        return events

    assert asyncio.run(run()) == [TurnStarted(TurnRef(turn.id))]
    assert gateway.media.inputs == [(3, 9)]
    assert gateway.rest.snapshot_reads == 1


def test_starts_turns_and_reports_an_already_active_turn() -> None:
    turn = _turn(1, VoiceTurnStatus.LISTENING)
    gateway = _Gateway(_snapshot(turn))
    gateway.rpc.voice.turn.started = VoiceTurnCommandResult(
        voiceSessionId=_VOICE_SESSION_ID, voiceTurnId=turn.id
    )

    async def run() -> TurnRef:
        started = await gateway.backend.start_turn(
            StartTurn(activation=ActivationKind.WAKE_WORD, pre_roll_sequence=4)
        )
        gateway.rpc.voice.turn.start_error = VoiceTurnAlreadyActiveError(
            -32000, "voice_turn_already_active", "busy"
        )
        with pytest.raises(TurnAlreadyActiveError):
            await gateway.backend.start_turn(
                StartTurn(activation=ActivationKind.MANUAL)
            )
        return started.turn

    assert asyncio.run(run()) == TurnRef(turn.id)
    assert gateway.rpc.voice.turn.start_calls == [
        (Activation.WAKE_WORD, 4),
        (Activation.MANUAL, None),
    ]


def test_maps_media_frames_to_their_turns() -> None:
    known = _turn(0, VoiceTurnStatus.SPEAKING)
    newer = _turn(2, VoiceTurnStatus.SPEAKING)
    gateway = _Gateway(
        _snapshot(known),
        frames=[
            _media(MediaFrameKind.OUTPUT_PCM, 0, b"\x01\x00"),
            _media(MediaFrameKind.OUTPUT_END, 0),
            # Older than every known turn: dropped without a refresh.
            _media(MediaFrameKind.OUTPUT_PCM, -1, b"\x02\x00"),
            _media(MediaFrameKind.OUTPUT_PCM, 2, b"\x03\x00"),
        ],
    )
    gateway.rest.snapshot = _snapshot(known, newer)

    assert _collect(gateway.backend.output_audio()) == [
        BackendAudioFrame(TurnRef(known.id), b"\x01\x00"),
        BackendAudioEnd(TurnRef(known.id)),
        BackendAudioFrame(TurnRef(newer.id), b"\x03\x00"),
    ]
    assert gateway.rest.snapshot_reads == 1


def test_close_is_idempotent() -> None:
    gateway = _Gateway(_snapshot())

    async def run() -> None:
        await gateway.backend.close()
        await gateway.backend.close()

    asyncio.run(run())

    assert gateway.rest.closed == [_VOICE_SESSION_ID]
    assert gateway.rpc.subscription.calls == [("unsubscribe", _SESSION_ID)]


def _collect[T](items: AsyncIterator[T]) -> list[T]:
    async def run() -> list[T]:
        return [item async for item in items]

    return asyncio.run(run())


def _snapshot(
    *turns: VoiceTurnResponse,
    active: VoiceTurnResponse | None = None,
    last_sequence: int = 0,
    session_id: UUID = _SESSION_ID,
) -> VoiceSessionSnapshotResponse:
    return VoiceSessionSnapshotResponse(
        voice_session=VoiceSessionResponse(
            id=_VOICE_SESSION_ID,
            session_id=session_id,
            room="office",
            status=VoiceSessionStatus.OPEN,
            input_format=_format(16_000),
            output_format=_format(24_000),
            media_path="/media",
            media_connected=True,
            created_at=_NOW,
            closed_at=None,
            close_reason=None,
        ),
        turns=list(turns),
        active_turn_id=None if active is None else active.id,
        last_sequence=last_sequence,
    )


def _format(sample_rate: int) -> GatewayAudioFormat:
    return GatewayAudioFormat(
        encoding=AudioEncoding.PCM_S16LE, sample_rate=sample_rate, channels=1
    )


def _turn(
    index: int, status: VoiceTurnStatus, *, turn_id: UUID | None = None
) -> VoiceTurnResponse:
    return VoiceTurnResponse(
        id=turn_id or uuid4(),
        index=index,
        activation=Activation.WAKE_WORD,
        status=status,
        transcript=None,
        user_message_id=None,
        error=None,
        started_at=_NOW,
        input_ended_at=None,
        transcribed_at=None,
        speech_started_at=None,
        ended_at=None,
    )


def _envelope(sequence: int, voice_session_id: UUID = _VOICE_SESSION_ID) -> dict:
    return {
        "event_id": uuid4(),
        "timestamp": _NOW,
        "voice_session_id": voice_session_id,
        "session_id": _SESSION_ID,
        "sequence": sequence,
    }


def _final(
    turn_id: UUID, *, sequence: int, voice_session_id: UUID = _VOICE_SESSION_ID
) -> VoiceTranscriptFinal:
    return VoiceTranscriptFinal(
        **_envelope(sequence, voice_session_id),
        voice_turn_id=turn_id,
        text="hello",
        user_message_id=uuid4(),
    )


def _partial(turn_id: UUID) -> VoiceTranscriptPartial:
    return VoiceTranscriptPartial(
        event_id=uuid4(),
        timestamp=_NOW,
        voice_session_id=_VOICE_SESSION_ID,
        voice_turn_id=turn_id,
        session_id=_SESSION_ID,
        revision=1,
        text="hel",
    )


def _turn_started(turn_id: UUID, *, sequence: int) -> VoiceTurnStarted:
    return VoiceTurnStarted(
        **_envelope(sequence), voice_turn_id=turn_id, activation=Activation.WAKE_WORD
    )


def _conversation_ended(*, sequence: int) -> VoiceConversationEnded:
    return VoiceConversationEnded(**_envelope(sequence), reason="idle")


def _closed(*, sequence: int) -> VoiceSessionClosed:
    return VoiceSessionClosed(**_envelope(sequence), reason="replaced")


def _media(kind: MediaFrameKind, turn_index: int, payload: bytes = b"") -> MediaFrame:
    return MediaFrame(
        kind=kind,
        voice_turn_index=turn_index,
        sequence=0,
        timestamp_ms=0,
        payload=payload,
    )
