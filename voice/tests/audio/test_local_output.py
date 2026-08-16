import asyncio
import struct

import voice.audio.device as device_module
from voice.audio.output import LocalAudioOutput


class _OutputStream:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.stopped = False
        self.closed = False

    def write(self, audio: bytes) -> None:
        self.writes.append(audio)

    def stop_stream(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class _PyAudio:
    def __init__(self) -> None:
        self.stream = _OutputStream()
        self.opened_with: dict[str, object] | None = None
        self.terminated = False

    def open(self, **options: object) -> _OutputStream:
        self.opened_with = options
        return self.stream

    def terminate(self) -> None:
        self.terminated = True


def test_local_output_streams_volume_adjusted_pcm_and_closes() -> None:
    async def run() -> _PyAudio:
        backend = _PyAudio()
        monkeypatch.setattr(device_module.pyaudio, "PyAudio", lambda: backend)
        output = LocalAudioOutput(trailing_silence_seconds=0)
        await output.set_volume(0.5)
        await output.start(sample_rate=16_000, channels=1)
        await output.play_chunk(struct.pack("<2h", 100, -100))
        await output.stop()
        return backend

    from pytest import MonkeyPatch

    monkeypatch = MonkeyPatch()
    try:
        backend = asyncio.run(run())
    finally:
        monkeypatch.undo()

    assert backend.stream.writes == [struct.pack("<2h", 50, -50)]
    assert backend.stream.stopped
    assert backend.stream.closed
    assert backend.terminated
