import pytest

import voice.audio.session as session_module
from voice.audio import PortAudioSession


class _PyAudio:
    def __init__(self) -> None:
        self.terminated = False

    def open(self, **options: object) -> object:
        return options

    def terminate(self) -> None:
        self.terminated = True


def test_context_manager_terminates_backend_and_cannot_be_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _PyAudio()
    monkeypatch.setattr(session_module.pyaudio, "PyAudio", lambda: backend)

    with PortAudioSession() as session:
        assert session.open_stream(output=True) == {"output": True}
        assert not backend.terminated

    assert backend.terminated
    with pytest.raises(RuntimeError, match="PortAudio session is closed"):
        session.open_stream(output=True)
