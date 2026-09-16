import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from gateway_rpc_client.models import (
    VoiceAssistantTextStarted,
    VoiceAssistantToolCompleted,
    VoiceAssistantToolStarted,
    VoiceTranscriptPartial,
    VoiceTurnCommandResult,
)
from gateway_rpc_client.models import (
    VoiceConversationEnded as GatewayVoiceConversationEnded,
)
from gateway_rpc_client.models import (
    VoiceConversationInactivityCountdown as GatewayVoiceConversationInactivityCountdown,
)
from gateway_rpc_client.models import (
    VoiceConversationStarted as GatewayVoiceConversationStarted,
)
from voice.activation import ActivationKind
from voice.audio import BufferedAudioInput
from voice.audio.ports import AudioInput
from voice.echo_cancellation import EchoPresence
from voice.events import (
    AssistantTextStarted,
    AssistantToolCompleted,
    AssistantToolStarted,
    UserSpeechStarted,
    VoiceConversationEnded,
    VoiceConversationInactivityCountdown,
    VoiceConversationStarted,
    VoiceTurnFailed,
)
from voice.events.bus import EventBus
from voice.events.models import Event, VoiceTurnEnded, VoiceTurnRequested
from voice.gateway.bridge import GatewayVoiceBridge
from voice.gateway.session import GatewayVoiceSession

_VOICE_SESSION_ID = uuid4()


class _Session:
    output_sample_rate = 24_000
    output_channels = 1
    active_turn = None

    def __init__(self) -> None:
        self._voice: asyncio.Queue[object] = asyncio.Queue()
        self.turn_id = uuid4()
        self.input_payloads: list[bytes] = []

    def emit(self, event: object) -> None:
        self._voice.put_nowait(event)

    async def voice_events(self) -> AsyncIterator[object]:
        while True:
            event = await self._voice.get()
            if isinstance(event, Exception):
                raise event
            yield event

    async def media_frames(self) -> AsyncIterator[object]:
        await asyncio.Event().wait()
        yield

    async def start_turn(self, activation, pre_roll_sequence) -> VoiceTurnCommandResult:
        return VoiceTurnCommandResult(
            voiceSessionId=_VOICE_SESSION_ID, voiceTurnId=self.turn_id
        )

    async def turn_index(self, voice_turn_id: UUID) -> int:
        return 1

    async def send_input(self, turn_index: int, sequence: int, payload: bytes) -> None:
        self.input_payloads.append(payload)

    async def end_input(self, turn_index: int, sequence: int) -> None:
        pass

    async def interrupt(self, voice_turn_id: UUID, input_sequence: int | None) -> None:
        pass

    async def playback_completed(self, voice_turn_id: UUID) -> None:
        pass


def test_user_speech_is_announced_only_once_the_gateway_hears_the_user(
    audio_input: AudioInput,
) -> None:
    async def run() -> tuple[int, int]:
        bus = EventBus()
        session = _Session()
        microphone = BufferedAudioInput(audio_input)
        bridge = GatewayVoiceBridge(bus, cast(GatewayVoiceSession, session), microphone)
        speech: list[UserSpeechStarted] = []
        bus.on(UserSpeechStarted, _record(speech))

        await microphone.start()
        await bridge.start()
        await bus.request(VoiceTurnRequested(activation=ActivationKind.MANUAL))
        await _settle()
        while_silent = len(speech)

        session.emit(_partial(session.turn_id, "hey"))
        await _settle()
        session.emit(_partial(session.turn_id, "hey there"))
        await _settle()

        await bridge.close()
        await microphone.stop()
        return while_silent, len(speech)

    while_silent, after_speaking = asyncio.run(run())

    assert while_silent == 0
    assert after_speaking == 1


def test_a_failing_stream_releases_the_active_turn(audio_input: AudioInput) -> None:
    async def run() -> tuple[UUID | None, list[VoiceTurnFailed], list[VoiceTurnEnded]]:
        bus = EventBus()
        session = _Session()
        microphone = BufferedAudioInput(audio_input)
        bridge = GatewayVoiceBridge(bus, cast(GatewayVoiceSession, session), microphone)
        failures: list[VoiceTurnFailed] = []
        ended: list[VoiceTurnEnded] = []
        bus.on(VoiceTurnFailed, _record(failures))
        bus.on(VoiceTurnEnded, _record(ended))

        await microphone.start()
        await bridge.start()
        await bus.request(VoiceTurnRequested(activation=ActivationKind.WAKE_WORD))
        await _settle()
        assert bridge.active_turn_id is not None

        session.emit(RuntimeError("the gateway stream is gone"))
        await _settle()

        await bridge.close()
        await microphone.stop()
        return bridge.active_turn_id, failures, ended

    active_turn_id, failures, ended = asyncio.run(run())

    assert active_turn_id is None
    assert [failure.message for failure in failures] == ["the gateway stream is gone"]
    assert len(ended) == 1


def test_an_activation_swallowed_by_an_open_turn_is_logged(
    audio_input: AudioInput,
    caplog,
) -> None:
    async def run() -> UUID:
        bus = EventBus()
        session = _Session()
        microphone = BufferedAudioInput(audio_input)
        bridge = GatewayVoiceBridge(bus, cast(GatewayVoiceSession, session), microphone)

        await microphone.start()
        await bridge.start()
        await bus.request(VoiceTurnRequested(activation=ActivationKind.WAKE_WORD))
        await _settle()
        await bus.request(VoiceTurnRequested(activation=ActivationKind.MANUAL))
        await _settle()

        await bridge.close()
        await microphone.stop()
        return session.turn_id

    with caplog.at_level(logging.WARNING, logger="voice.gateway.bridge"):
        turn_id = asyncio.run(run())

    assert caplog.messages == [
        f"Ignoring the manual activation: voice turn {turn_id} never ended"
    ]


def test_gateway_conversation_events_are_forwarded_to_the_local_bus(
    audio_input: AudioInput,
) -> None:
    async def run() -> tuple[list[int], list[str]]:
        bus = EventBus()
        session = _Session()
        microphone = BufferedAudioInput(audio_input)
        bridge = GatewayVoiceBridge(bus, cast(GatewayVoiceSession, session), microphone)
        started: list[VoiceConversationStarted] = []
        countdowns: list[VoiceConversationInactivityCountdown] = []
        ended: list[VoiceConversationEnded] = []
        bus.on(VoiceConversationStarted, _record(started))
        bus.on(VoiceConversationInactivityCountdown, _record(countdowns))
        bus.on(VoiceConversationEnded, _record(ended))

        await microphone.start()
        await bridge.start()
        event_id = uuid4()
        timestamp = datetime.now(UTC)
        session_id = uuid4()
        session.emit(
            GatewayVoiceConversationStarted(
                event_id=event_id,
                timestamp=timestamp,
                voice_session_id=_VOICE_SESSION_ID,
                session_id=session_id,
                sequence=1,
            )
        )
        session.emit(
            GatewayVoiceConversationInactivityCountdown(
                event_id=event_id,
                timestamp=timestamp,
                voice_session_id=_VOICE_SESSION_ID,
                session_id=session_id,
                sequence=2,
                remaining_seconds=3,
            )
        )
        session.emit(
            GatewayVoiceConversationEnded(
                event_id=event_id,
                timestamp=timestamp,
                voice_session_id=_VOICE_SESSION_ID,
                session_id=session_id,
                sequence=3,
                reason="inactivity_timeout",
            )
        )
        await _settle()

        await bridge.close()
        await microphone.stop()
        assert len(started) == 1
        return [event.remaining_seconds for event in countdowns], [
            event.reason for event in ended
        ]

    countdowns, reasons = asyncio.run(run())

    assert countdowns == [3]
    assert reasons == ["inactivity_timeout"]


def test_gateway_assistant_activity_is_forwarded_to_the_local_bus(
    audio_input: AudioInput,
) -> None:
    async def run() -> tuple[UUID, list[Event]]:
        bus = EventBus()
        session = _Session()
        microphone = BufferedAudioInput(audio_input)
        bridge = GatewayVoiceBridge(bus, cast(GatewayVoiceSession, session), microphone)
        forwarded: list[Event] = []
        bus.on(AssistantTextStarted, _record(forwarded))
        bus.on(AssistantToolStarted, _record(forwarded))
        bus.on(AssistantToolCompleted, _record(forwarded))

        await microphone.start()
        await bridge.start()
        base = {
            "event_id": uuid4(),
            "timestamp": datetime.now(UTC),
            "voice_session_id": _VOICE_SESSION_ID,
            "voice_turn_id": session.turn_id,
            "session_id": uuid4(),
        }
        session.emit(VoiceAssistantToolStarted(**base, sequence=1, name="weather"))
        session.emit(VoiceAssistantToolCompleted(**base, sequence=2, name="weather"))
        session.emit(VoiceAssistantTextStarted(**base, sequence=3))
        await _settle()

        await bridge.close()
        await microphone.stop()
        return session.turn_id, forwarded

    turn_id, forwarded = asyncio.run(run())

    assert forwarded == [
        AssistantToolStarted(turn_id=turn_id, name="weather"),
        AssistantToolCompleted(turn_id=turn_id, name="weather"),
        AssistantTextStarted(turn_id=turn_id),
    ]


def test_playback_echo_is_not_uploaded_as_user_audio() -> None:
    async def run() -> list[bytes]:
        bus = EventBus()
        session = _Session()
        source = _StreamingAudioInput()
        echo = _EchoPresence()
        microphone = BufferedAudioInput(
            source,
            echo_presence=cast(EchoPresence, echo),
        )
        bridge = GatewayVoiceBridge(
            bus,
            cast(GatewayVoiceSession, session),
            microphone,
            max_echo_confidence=0.5,
        )

        await microphone.start()
        await bridge.start()
        await bus.request(VoiceTurnRequested(activation=ActivationKind.MANUAL))

        echo.confidence = 0.8
        source.emit(b"assistant echo")
        await _settle()
        echo.confidence = 0.1
        source.emit(b"user speech")
        await _settle()

        await bridge.close()
        await microphone.stop()
        return session.input_payloads

    assert asyncio.run(run()) == [b"user speech"]


def _partial(voice_turn_id: UUID, text: str) -> VoiceTranscriptPartial:
    return VoiceTranscriptPartial(
        event_id=uuid4(),
        timestamp=datetime.now(UTC),
        voice_session_id=_VOICE_SESSION_ID,
        session_id=uuid4(),
        voice_turn_id=voice_turn_id,
        revision=1,
        text=text,
    )


def _record[E](collected: list[E]):
    async def record(event: E) -> None:
        collected.append(event)

    return record


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


class _StreamingAudioInput(AudioInput):
    def __init__(self) -> None:
        self._active = False
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()

    @property
    def sample_rate(self) -> int:
        return 16_000

    @property
    def channels(self) -> int:
        return 1

    @property
    def frames_per_chunk(self) -> int:
        return 1_280

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        self._active = True

    async def stop(self) -> None:
        self._active = False

    async def stream_chunks(self) -> AsyncIterator[bytes]:
        while self._active:
            yield await self._chunks.get()

    def emit(self, chunk: bytes) -> None:
        self._chunks.put_nowait(chunk)


class _EchoPresence:
    def __init__(self) -> None:
        self.confidence = 0.0

    @property
    def echo_confidence(self) -> float:
        return self.confidence
