import asyncio
import wave
from pathlib import Path

import pytest

from voice.events.listener import Earcon, EarconPlayer
from voice.events.listener.sound_listener import _DEFAULT_SOUNDS_DIR as _SOUNDS_DIR


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


def test_player_warms_cache_and_play_uses_cached_wav_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sounds = {earcon: str(earcon).encode() for earcon in Earcon}
    for earcon, audio in sounds.items():
        (tmp_path / f"{earcon}.wav").write_bytes(audio)

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
        assert reads == len(Earcon)
        await earcons.play(Earcon.WAKE)
        await earcons.play(Earcon.WAKE)
        return player

    player = asyncio.run(run())

    assert player.audio == [sounds[Earcon.WAKE], sounds[Earcon.WAKE]]
    assert reads == len(Earcon)
