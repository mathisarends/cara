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


class SilencingEchoCanceller:
    sample_rate = 16000
    channels = 1

    def analyze_render(
        self,
        pcm: bytes,
        *,
        sample_rate: int,
        channels: int,
        sample_width: int,
    ) -> None:
        pass

    def process_capture(self, pcm: bytes) -> bytes:
        return bytes(len(pcm))


def test_recorder_detects_voice_only_after_echo_cancellation(monkeypatch) -> None:
    cancel = threading.Event()
    stream = CancellingInputStream(cancel)
    pa = RecordingPyAudio(stream)
    monkeypatch.setattr(recorder_module.pyaudio, "PyAudio", lambda: pa)
    speech_started = False

    def mark_speech_started() -> None:
        nonlocal speech_started
        speech_started = True

    recorder = MicrophoneRecorder(
        MicrophoneInputSettings(chunk=160),
        echo_canceller=SilencingEchoCanceller(),
    )

    audio = recorder._record_until_silence_sync(
        speech_started=mark_speech_started,
        cancel=cancel,
    )

    assert audio is None
    assert speech_started is False
    assert stream.stopped is True
    assert stream.closed is True
    assert pa.terminated is True
