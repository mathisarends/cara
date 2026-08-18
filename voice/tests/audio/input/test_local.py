import asyncio
from collections.abc import Callable
from typing import Protocol, cast
from unittest.mock import Mock

import pyaudio
import pytest

import voice.audio.input.local as local_module
from voice.audio.input import MicrophoneAudioInput
from voice.audio.session import PortAudioSession


class _Stream(Protocol):
    stop_stream: Mock
    close: Mock


class _Session(Protocol):
    streams: list[object]
    open_calls: list[dict[str, object]]
    closed: bool


@pytest.mark.parametrize(
    ("argument", "value", "message"),
    [
        ("sample_rate", 0, "sample_rate must be positive"),
        ("channels", 0, "channels must be positive"),
        ("frames_per_chunk", 0, "frames_per_chunk must be positive"),
    ],
)
def test_rejects_invalid_audio_format(argument: str, value: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        MicrophoneAudioInput(**{argument: value})


def test_starts_streams_and_stops_an_injected_session(
    audio_session: _Session,
    stream_factory: Callable[..., _Stream],
) -> None:
    stream = stream_factory(b"chunk")
    audio_session.streams.append(stream)
    microphone = MicrophoneAudioInput(
        sample_rate=24_000,
        channels=2,
        frames_per_chunk=480,
        session=cast(PortAudioSession, audio_session),
    )

    async def run() -> None:
        await microphone.start()
        await microphone.start()
        assert await anext(microphone.stream_chunks()) == b"chunk"
        await microphone.stop()
        await microphone.stop()

    asyncio.run(run())

    assert microphone.sample_rate == 24_000
    assert microphone.channels == 2
    assert microphone.frames_per_chunk == 480
    assert not microphone.is_active
    assert audio_session.open_calls == [
        {
            "rate": 24_000,
            "channels": 2,
            "format": pyaudio.paInt16,
            "input": True,
            "frames_per_buffer": 480,
        }
    ]
    stream.stop_stream.assert_called_once_with()
    stream.close.assert_called_once_with()
    assert not audio_session.closed


def test_streaming_requires_an_active_input() -> None:
    microphone = MicrophoneAudioInput()

    with pytest.raises(RuntimeError, match="not active"):
        asyncio.run(anext(microphone.stream_chunks()))


def test_closes_an_owned_session(
    audio_session: _Session,
    stream_factory: Callable[..., _Stream],
    monkeypatch,
) -> None:
    stream = stream_factory(active=False)
    audio_session.streams.append(stream)
    monkeypatch.setattr(local_module, "PortAudioSession", lambda: audio_session)
    microphone = MicrophoneAudioInput()

    async def run() -> None:
        await microphone.start()
        await microphone.stop()

    asyncio.run(run())

    stream.stop_stream.assert_not_called()
    assert audio_session.closed


def test_recovers_from_input_overflow(
    audio_session: _Session,
    stream_factory: Callable[..., _Stream],
    caplog,
) -> None:
    overflow = OSError(-9988, "overflow")
    failed_stream = stream_factory(overflow)
    replacement = stream_factory(b"recovered")
    audio_session.streams.extend([failed_stream, replacement])
    microphone = MicrophoneAudioInput(session=cast(PortAudioSession, audio_session))

    async def run() -> None:
        await microphone.start()
        assert await anext(microphone.stream_chunks()) == b"recovered"
        await microphone.stop()

    asyncio.run(run())

    assert len(audio_session.open_calls) == 2
    failed_stream.close.assert_called_once_with()
    assert "Audio input overflow" in caplog.text


def test_propagates_unexpected_read_errors(
    audio_session: _Session,
    stream_factory: Callable[..., _Stream],
) -> None:
    audio_session.streams.append(stream_factory(OSError(5, "device failed")))
    microphone = MicrophoneAudioInput(session=cast(PortAudioSession, audio_session))

    async def run() -> None:
        await microphone.start()
        with pytest.raises(OSError, match="device failed"):
            await anext(microphone.stream_chunks())
        await microphone.stop()

    asyncio.run(run())
