import asyncio
import wave
from pathlib import Path

import pytest

from voice import Earcon, SoundObserver
from voice.events import AudioPlaybackRequested
from voice.events.bus import EventBus
from voice.observer import ObserverContext
from voice.sound import _DEFAULT_SOUNDS_DIR as _SOUNDS_DIR


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
        event_bus = EventBus()
        requested: list[bytes] = []

        async def capture(request: AudioPlaybackRequested) -> None:
            requested.append(request.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)
        observer = SoundObserver(sounds_dir=tmp_path)
        assert reads == 0
        await observer.prepare(ObserverContext(event_bus=event_bus))
        assert reads == len(Earcon)
        await observer.on_wake_word_detected("hey_mycroft", 0.9, 1)
        await observer.on_wake_word_detected("hey_mycroft", 0.9, 1)
        return requested

    requested = asyncio.run(run())

    assert requested == [sounds[Earcon.WAKE], sounds[Earcon.WAKE]]
    assert reads == len(Earcon)
