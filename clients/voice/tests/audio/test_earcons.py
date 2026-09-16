import asyncio
import wave
from pathlib import Path

import pytest

from voice import Earcon, SoundIntegration
from voice.audio import AudioPlayback
from voice.integration import VoiceIntegrationContext
from voice.sound import _DEFAULT_SOUNDS_DIR as _SOUNDS_DIR


class _RecordingAudioPlayer(AudioPlayback):
    def __init__(self) -> None:
        self.audio: list[bytes] = []

    async def play(self, audio: bytes) -> None:
        self.audio.append(audio)


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

    async def run() -> list[bytes]:
        audio_player = _RecordingAudioPlayer()
        integration = SoundIntegration(sounds_dir=tmp_path)
        assert reads == 0
        await integration.prepare(VoiceIntegrationContext(audio_player=audio_player))
        assert reads == len(Earcon)
        await integration.on_wake_word_detected("hey_mycroft", 0.9, 1)
        await integration.on_wake_word_detected("hey_mycroft", 0.9, 1)
        return audio_player.audio

    requested = asyncio.run(run())

    assert requested == [sounds[Earcon.WAKE], sounds[Earcon.WAKE]]
    assert reads == len(Earcon)
