import asyncio
import logging
import wave
from pathlib import Path

import pytest

from cara.audio import Earcon, EarconPlayer

_SOUNDS_DIR = Path(__file__).resolve().parent.parent.parent / "sounds"


class RecordingAudioPlayer:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.audio: list[bytes] = []
        self._error = error

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self.audio.append(audio)
        if self._error is not None:
            raise self._error


@pytest.mark.parametrize("earcon", list(Earcon))
def test_earcon_asset_is_16_bit_pcm_wav(earcon: Earcon) -> None:
    path = _SOUNDS_DIR / f"{earcon}.wav"

    assert path.is_file()
    with wave.open(str(path)) as audio:
        assert audio.getsampwidth() == 2


def test_play_uses_wav_bytes_and_caches_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    expected = b"wav audio"
    path = tmp_path / "wake.wav"
    path.write_bytes(expected)
    reads = 0
    original_read_bytes = Path.read_bytes

    def count_read_bytes(candidate: Path) -> bytes:
        nonlocal reads
        reads += 1
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", count_read_bytes)

    async def run() -> RecordingAudioPlayer:
        player = RecordingAudioPlayer()
        earcons = EarconPlayer(player, sounds_dir=tmp_path)
        await earcons.play(Earcon.WAKE)
        await earcons.play(Earcon.WAKE)
        return player

    player = asyncio.run(run())

    assert player.audio == [expected, expected]
    assert reads == 1


def test_play_soon_returns_before_playback_and_logs_errors(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "interrupt.wav").write_bytes(b"interrupt")

    async def run() -> RecordingAudioPlayer:
        player = RecordingAudioPlayer(error=RuntimeError("speaker failed"))
        earcons = EarconPlayer(player, sounds_dir=tmp_path)
        earcons.play_soon(Earcon.INTERRUPT)
        assert player.audio == []
        await asyncio.sleep(0)
        return player

    with caplog.at_level(logging.ERROR):
        player = asyncio.run(run())

    assert player.audio == [b"interrupt"]
    assert "Failed to play earcon interrupt" in caplog.text
