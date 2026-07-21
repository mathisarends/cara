import threading

from cara.audio import recorder as recorder_module
from cara.audio.recorder import MicrophoneInputSettings, MicrophoneRecorder


class CancellingInputStream:
    def __init__(self, cancel: threading.Event) -> None:
        self._cancel = cancel
        self.stopped = False
        self.closed = False

    def read(self, chunk: int, *, exception_on_overflow: bool) -> bytes:
        self._cancel.set()
        return b"\xff\x7f" * chunk

    def stop_stream(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class RecordingPyAudio:
    def __init__(self, stream: CancellingInputStream) -> None:
        self.stream = stream
        self.terminated = False

    def open(self, **kwargs: object) -> CancellingInputStream:
        return self.stream

    def terminate(self) -> None:
        self.terminated = True


def test_recorder_stops_when_cancelled_before_speech(monkeypatch) -> None:
    cancel = threading.Event()
    stream = CancellingInputStream(cancel)
    pa = RecordingPyAudio(stream)
    monkeypatch.setattr(recorder_module.pyaudio, "PyAudio", lambda: pa)
    recorder = MicrophoneRecorder(MicrophoneInputSettings(chunk=160))

    audio = recorder._record_until_silence_sync(
        cancel=cancel,
    )

    assert audio is None
    assert stream.stopped is True
    assert stream.closed is True
    assert pa.terminated is True
