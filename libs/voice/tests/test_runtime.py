import asyncio
from collections.abc import Awaitable, Callable
from typing import Self
from uuid import uuid4

import pytest
from doubles import (
    CHUNK,
    EndInput,
    FakeVoiceBackend,
    Interrupt,
    ManualActivationSource,
    ManualBargeIn,
    PlaybackCompleted,
    RecordingAudioOutput,
    RecordingObserver,
    StreamingAudioInput,
    settle,
)

from voice.activation import ActivationKind, ListenActivation
from voice.audio import BufferedAudioInput
from voice.backend import (
    ActiveTurn,
    BackendAudioEnd,
    BackendAudioFrame,
    BackendSessionState,
    BackendStreamEndedError,
    SessionClosed,
    StartTurn,
    TranscriptCompleted,
    TranscriptUpdated,
    TurnCompleted,
    TurnPhase,
    TurnRef,
    TurnStarted,
)
from voice.barge_in import BargeInStrategy, WakeWordBargeIn
from voice.lifecycle import VoiceTurnFailed
from voice.runtime import VoiceRuntime
from voice.wakeword import WakeWordDetection


class _Harness:
    def __init__(
        self,
        *,
        initial_state: BackendSessionState | None = None,
        barge_in: BargeInStrategy | None = None,
        accept_activations: Callable[[], bool] | None = None,
    ) -> None:
        self.backend = FakeVoiceBackend(initial_state)
        self.microphone = StreamingAudioInput()
        self.output = RecordingAudioOutput()
        self.activations = ManualActivationSource()
        self.barge_in = barge_in or ManualBargeIn()
        self.observer = RecordingObserver()
        self.runtime = VoiceRuntime(
            backend=self.backend,
            audio_input=BufferedAudioInput(self.microphone),
            audio_output=self.output,
            activation_sources=(self.activations,),
            barge_in=self.barge_in,
            observers=(self.observer,),
            accept_activations=accept_activations,
        )
        self._run: asyncio.Task[None] | None = None
        self._awaited = False

    async def __aenter__(self) -> Self:
        self._run = asyncio.create_task(self.runtime.run())
        await settle()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.runtime.stop()
        if not self._awaited:
            await self.finished()

    async def finished(self) -> None:
        assert self._run is not None
        self._awaited = True
        await asyncio.wait_for(self._run, timeout=1)

    def capture(self, chunks: int) -> None:
        for _ in range(chunks):
            self.microphone.emit(CHUNK)

    async def activate(self, sequence: int) -> TurnRef:
        self.activations.activate(
            ListenActivation(sequence=sequence, kind=ActivationKind.WAKE_WORD)
        )
        await settle()
        return self.backend.started_turns[-1]

    async def respond(self, turn: TurnRef) -> None:
        self.backend.emit(TranscriptCompleted(turn))
        await settle()
        self.backend.emit_audio(BackendAudioFrame(turn, CHUNK))
        await settle()


def _run(scenario: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(scenario())


def test_runs_a_turn_from_activation_to_playback_acknowledgement() -> None:
    async def scenario() -> None:
        async with _Harness() as harness:
            harness.capture(3)
            await settle()
            turn = await harness.activate(sequence=2)

            assert harness.backend.start_requests == [
                StartTurn(activation=ActivationKind.WAKE_WORD, pre_roll_sequence=2)
            ]
            assert [sequence for _, sequence in harness.backend.inputs] == [1, 2]

            harness.backend.emit(TurnStarted(turn))
            harness.backend.emit(TranscriptUpdated(turn))
            harness.backend.emit(TranscriptUpdated(turn))
            await harness.respond(turn)
            harness.backend.emit_audio(BackendAudioEnd(turn))
            await settle()

            assert harness.output.chunks == [CHUNK]
            assert harness.backend.commands == [PlaybackCompleted(turn)]

            harness.backend.emit(TurnCompleted(turn))
            await settle()

        assert harness.observer.names == [
            "SessionStarted",
            "UserTurnStarted",
            "UserSpeechStarted",
            "UserSpeechEnded",
            "AssistantTurnStarted",
            "AssistantSpeechStarted",
            "AssistantSpeechCompleted",
            "VoiceTurnEnded",
            "SessionStopped",
        ]

    _run(scenario)


def test_ignores_activations_while_embedding_process_is_not_ready() -> None:
    async def scenario() -> None:
        async with _Harness(accept_activations=lambda: False) as harness:
            harness.activations.activate(ListenActivation(sequence=1))
            await settle()

            assert harness.backend.start_requests == []

    _run(scenario)


def test_rejects_an_activation_while_a_turn_is_active(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        async with _Harness() as harness:
            harness.capture(1)
            await settle()
            await harness.activate(sequence=0)
            harness.activations.activate(
                ListenActivation(
                    sequence=0,
                    kind=ActivationKind.WAKE_WORD,
                    detection=WakeWordDetection(sequence=0, score=0.9, name="jarvis"),
                )
            )
            await settle()

            assert len(harness.backend.start_requests) == 1
            assert "WakeWordDetected" in harness.observer.names

    with caplog.at_level("INFO", logger="voice.runtime"):
        _run(scenario)

    assert "Ignoring the wake_word activation" in caplog.text


def test_barge_in_is_ignored_while_the_user_holds_the_floor() -> None:
    async def scenario() -> None:
        barge_in = ManualBargeIn()
        async with _Harness(barge_in=barge_in) as harness:
            await harness.activate(sequence=0)
            barge_in.signal(sequence=0)
            await settle()

            assert harness.backend.commands == []
            assert "VoiceTurnInterrupted" not in harness.observer.names

    _run(scenario)


def test_barge_in_interrupts_the_response_and_starts_a_new_turn() -> None:
    async def scenario() -> None:
        barge_in = ManualBargeIn()
        async with _Harness(barge_in=barge_in) as harness:
            turn = await harness.activate(sequence=0)
            await harness.respond(turn)

            barge_in.signal(sequence=7)
            await settle()

            assert harness.backend.commands == [Interrupt(turn, 7)]
            assert harness.backend.start_requests[-1] == StartTurn(
                activation=ActivationKind.BARGE_IN, pre_roll_sequence=7
            )
            assert harness.output.clear_calls >= 1
            names = harness.observer.names
            assert names.index("VoiceTurnInterrupted") < names.index("VoiceTurnEnded")
            assert names.count("UserTurnStarted") == 2

    _run(scenario)


def test_wake_word_barge_in_interrupts_through_the_activation() -> None:
    async def scenario() -> None:
        async with _Harness(barge_in=WakeWordBargeIn()) as harness:
            turn = await harness.activate(sequence=0)
            await harness.respond(turn)

            await harness.activate(sequence=4)

            assert harness.backend.commands == [Interrupt(turn, 4)]
            assert harness.backend.start_requests[-1] == StartTurn(
                activation=ActivationKind.BARGE_IN, pre_roll_sequence=4
            )

    _run(scenario)


def test_a_proactive_turn_waits_for_the_assistant_without_uploading() -> None:
    async def scenario() -> None:
        async with _Harness() as harness:
            harness.capture(2)
            turn = TurnRef(uuid4())
            harness.backend.emit(TurnStarted(turn, proactive=True))
            await settle()
            harness.backend.emit_audio(BackendAudioFrame(turn, CHUNK))
            harness.backend.emit_audio(BackendAudioEnd(turn))
            await settle()

            assert harness.backend.inputs == []
            assert harness.output.chunks == [CHUNK]
            assert harness.backend.commands == [PlaybackCompleted(turn)]
            assert "UserTurnStarted" not in harness.observer.names

    _run(scenario)


def test_restores_a_listening_turn_by_capturing_live_audio() -> None:
    async def scenario() -> None:
        turn = TurnRef(uuid4())
        state = BackendSessionState(ActiveTurn(turn, TurnPhase.LISTENING))
        async with _Harness(initial_state=state) as harness:
            harness.capture(2)
            await settle()

            assert harness.backend.inputs == [(turn, 0), (turn, 1)]
            assert harness.observer.names[:2] == ["SessionStarted", "UserTurnStarted"]

    _run(scenario)


def test_restores_a_speaking_turn_by_playing_its_response() -> None:
    async def scenario() -> None:
        turn = TurnRef(uuid4())
        state = BackendSessionState(ActiveTurn(turn, TurnPhase.SPEAKING))
        async with _Harness(initial_state=state) as harness:
            harness.backend.emit_audio(BackendAudioFrame(turn, CHUNK))
            harness.backend.emit_audio(BackendAudioEnd(turn))
            await settle()

            assert harness.backend.inputs == []
            assert harness.backend.commands == [PlaybackCompleted(turn)]

    _run(scenario)


def test_an_activation_timeout_ends_the_turn_input() -> None:
    async def scenario() -> None:
        async with _Harness() as harness:
            harness.activations.activate(ListenActivation(speech_start_timeout=0.01))
            await asyncio.sleep(0.05)
            await settle()
            turn = harness.backend.started_turns[0]

            assert harness.backend.commands == [EndInput(turn, 0)]

    _run(scenario)


def test_a_failed_upload_fails_and_ends_the_turn() -> None:
    async def scenario() -> None:
        async with _Harness() as harness:
            harness.backend.input_error = ConnectionError("upload lost")
            turn = await harness.activate(sequence=0)
            harness.capture(1)
            await settle()

            assert harness.backend.commands == [Interrupt(turn, None)]
            failure = next(
                event
                for event in harness.observer.events
                if isinstance(event, VoiceTurnFailed)
            )
            assert failure.message == "upload lost"
            assert harness.observer.names[-1] == "VoiceTurnEnded"

    _run(scenario)


def test_a_backend_failure_releases_the_turn_and_raises() -> None:
    async def scenario() -> None:
        harness = _Harness()
        async with harness:
            turn = await harness.activate(sequence=0)
            harness.backend.emit(ConnectionError("gateway gone"))
            with pytest.raises(ConnectionError, match="gateway gone"):
                await harness.finished()

        assert harness.backend.commands == [Interrupt(turn, None)]
        assert harness.observer.names[-3:] == [
            "VoiceTurnFailed",
            "VoiceTurnEnded",
            "SessionStopped",
        ]
        assert harness.microphone.stop_calls == 1
        assert harness.output.stop_calls == 1
        assert _leftover_tasks() == set()

    _run(scenario)


def test_a_capture_failure_raises_from_run() -> None:
    async def scenario() -> None:
        harness = _Harness()
        async with harness:
            harness.microphone.emit(OSError("microphone unplugged"))
            with pytest.raises(OSError, match="microphone unplugged"):
                await harness.finished()

        assert _leftover_tasks() == set()

    _run(scenario)


def test_an_ended_event_stream_is_an_error() -> None:
    async def scenario() -> None:
        harness = _Harness()
        async with harness:
            harness.backend.emit(None)
            with pytest.raises(BackendStreamEndedError):
                await harness.finished()

    _run(scenario)


def test_a_closed_backend_session_ends_the_run_normally() -> None:
    async def scenario() -> None:
        harness = _Harness()
        async with harness:
            harness.backend.emit(SessionClosed(reason="replaced"))
            await harness.finished()

        assert harness.observer.names == ["SessionStarted", "SessionStopped"]

    _run(scenario)


def test_stop_is_idempotent_and_run_only_runs_once() -> None:
    async def scenario() -> None:
        harness = _Harness()
        async with harness:
            pass
        await harness.runtime.stop()

        with pytest.raises(RuntimeError):
            await harness.runtime.run()
        assert harness.microphone.stop_calls == 1

    _run(scenario)


def _leftover_tasks() -> set[asyncio.Task[object]]:
    return asyncio.all_tasks() - {asyncio.current_task()}
