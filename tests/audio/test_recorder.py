import threading

from cara.audio.recorder import MicrophoneInputSettings, MicrophoneRecorder


class CancellingMicrophone:
    rate = 16000
    channels = 1

    def __init__(self, cancel: threading.Event) -> None:
        self._cancel = cancel
        self.reads = 0

    def read(self, num_frames: int) -> bytes:
        self.reads += 1
        self._cancel.set()
        return b"\xff\x7f" * num_frames


def test_recorder_stops_when_cancelled_before_speech() -> None:
    cancel = threading.Event()
    microphone = CancellingMicrophone(cancel)
    recorder = MicrophoneRecorder(microphone, MicrophoneInputSettings(chunk=160))

    audio = recorder._record_until_silence_sync(cancel=cancel)

    assert audio is None
    assert microphone.reads >= 1
