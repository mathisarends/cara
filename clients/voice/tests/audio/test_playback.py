import asyncio
from uuid import uuid4

from doubles import CHUNK, RecordingAudioOutput, settle

from voice.audio import AudioFormat
from voice.audio.playback import (
    PlaybackController,
    PlaybackFinished,
    PlaybackSignal,
    PlaybackStarted,
)
from voice.backend import BackendAudioEnd, BackendAudioFrame, TurnRef


class _FailingOutput(RecordingAudioOutput):
    async def play_chunk(self, chunk: bytes) -> None:
        raise OSError("speaker gone")


def _controller(
    output: RecordingAudioOutput,
) -> tuple[PlaybackController, list[PlaybackSignal]]:
    signals: list[PlaybackSignal] = []
    controller = PlaybackController(
        output, audio_format=AudioFormat(sample_rate=24_000), notify=signals.append
    )
    return controller, signals


def test_plays_the_selected_turn_and_reports_start_and_finish() -> None:
    output = RecordingAudioOutput()
    turn = TurnRef(uuid4())

    async def run() -> list[PlaybackSignal]:
        controller, signals = _controller(output)
        await controller.select(turn)
        await controller.accept(BackendAudioFrame(turn, CHUNK))
        await controller.accept(BackendAudioEnd(turn))
        await settle()
        return signals

    assert asyncio.run(run()) == [PlaybackStarted(turn), PlaybackFinished(turn)]
    assert output.chunks == [CHUNK]


def test_drops_audio_of_turns_that_are_not_selected() -> None:
    output = RecordingAudioOutput()
    selected, other = TurnRef(uuid4()), TurnRef(uuid4())

    async def run() -> list[PlaybackSignal]:
        controller, signals = _controller(output)
        await controller.select(selected)
        await controller.accept(BackendAudioFrame(other, CHUNK))
        await controller.accept(BackendAudioEnd(other))
        await settle()
        return signals

    assert asyncio.run(run()) == []
    assert output.chunks == []


def test_selecting_another_turn_cancels_the_current_response() -> None:
    output = RecordingAudioOutput()
    first, second = TurnRef(uuid4()), TurnRef(uuid4())

    async def run() -> list[PlaybackSignal]:
        controller, signals = _controller(output)
        await controller.select(first)
        await controller.accept(BackendAudioFrame(first, CHUNK))
        await settle()
        await controller.select(second)
        await controller.accept(BackendAudioEnd(first))
        await settle()
        return signals

    assert asyncio.run(run()) == [PlaybackStarted(first)]
    assert output.clear_calls == 1


def test_an_output_failure_finishes_the_response_with_the_error() -> None:
    turn = TurnRef(uuid4())

    async def run() -> list[PlaybackSignal]:
        controller, signals = _controller(_FailingOutput())
        await controller.select(turn)
        await controller.accept(BackendAudioFrame(turn, CHUNK))
        await settle()
        return signals

    signals = asyncio.run(run())

    assert signals[-1].turn == turn
    assert isinstance(signals[-1], PlaybackFinished)
    assert isinstance(signals[-1].error, OSError)


def test_interrupt_clears_the_output_and_drops_later_audio() -> None:
    output = RecordingAudioOutput()
    turn = TurnRef(uuid4())

    async def run() -> None:
        controller, _ = _controller(output)
        await controller.select(turn)
        await controller.interrupt()
        await controller.accept(BackendAudioFrame(turn, CHUNK))
        await settle()

    asyncio.run(run())

    assert output.chunks == []
    assert output.clear_calls == 1
