import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

from gateway_rpc_client.models import VoiceTranscriptPartial, VoiceTurnCommandResult
from voice.activation import ActivationKind
from voice.audio import BufferedAudioInput
from voice.audio.ports import AudioInput
from voice.events import UserSpeechStarted, VoiceTurnFailed
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded, VoiceTurnRequested
from voice.gateway.bridge import GatewayVoiceBridge

_VOICE_SESSION_ID = uuid4()


class _Session:
    output_sample_rate = 24_000
    output_channels = 1
    active_turn = None

    def __init__(self) -> None:
        self._voice: asyncio.Queue[object] = asyncio.Queue()
        self.turn_id = uuid4()

    def emit(self, event: object) -> None:
        self._voice.put_nowait(event)

    async def voice_events(self) -> AsyncIterator[object]:
        while True:
            event = await self._voice.get()
            if isinstance(event, Exception):
                raise event
            yield event

    async def conversation_events(self) -> AsyncIterator[object]:
        await asyncio.Event().wait()
        yield

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
        pass

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
        bridge = GatewayVoiceBridge(bus, session, microphone)
        speech: list[UserSpeechStarted] = []
        bus.on(UserSpeechStarted, _record(speech))

        await microphone.start()
        await bridge.start()
        await bus.request(
            VoiceTurnRequested(
                activation=ActivationKind.FOLLOW_UP,
                speech_start_timeout=5.0,
            )
        )
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
        bridge = GatewayVoiceBridge(bus, session, microphone)
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
        bridge = GatewayVoiceBridge(bus, session, microphone)

        await microphone.start()
        await bridge.start()
        await bus.request(VoiceTurnRequested(activation=ActivationKind.WAKE_WORD))
        await _settle()
        await bus.request(VoiceTurnRequested(activation=ActivationKind.FOLLOW_UP))
        await _settle()

        await bridge.close()
        await microphone.stop()
        return session.turn_id

    with caplog.at_level(logging.WARNING, logger="voice.gateway.bridge"):
        turn_id = asyncio.run(run())

    assert caplog.messages == [
        f"Ignoring the follow_up activation: voice turn {turn_id} never ended"
    ]


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
