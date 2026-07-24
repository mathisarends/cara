import asyncio
import struct

import cara.audio.sonos.player as player_module
from cara.audio.sonos import SonosAudioPlayer, SonosSettings
from cara.audio.sonos.player import _wav_duration


def _wav(*, declared_frames: int, data_bytes: int, rate: int = 24000) -> bytes:
    block = 2  # mono, 16-bit
    header = b"RIFF" + struct.pack("<I", 36 + data_bytes) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * block, block, 16)
    header += b"data" + struct.pack("<I", declared_frames * block)
    return header + b"\x00" * data_bytes


class FakePlayer:
    def __init__(self, player_id: str) -> None:
        self.id = player_id


class FakeVolumeState:
    def __init__(self, volume: int) -> None:
        self.volume = volume


class FakeClip:
    def __init__(self, clip_id: str) -> None:
        self.id = clip_id


class FakeSonosCloudClient:
    def __init__(self, volume: int = 50) -> None:
        self._volume = volume
        self.played: list[str] = []
        self.cancelled: list[str] = []

    async def resolve_player(self, name: str) -> FakePlayer:
        return FakePlayer("RINCON_TEST")

    async def get_player_volume(self, player_id: str) -> FakeVolumeState:
        return FakeVolumeState(self._volume)

    async def set_player_volume(self, player_id: str, *, volume: int) -> None:
        self._volume = max(0, min(100, volume))

    async def play_audio_clip(self, player_id: str, stream_url: str, **kwargs: object) -> FakeClip:
        self.played.append(stream_url)
        return FakeClip("clip-1")

    async def cancel_audio_clip(self, player_id: str, clip_id: str) -> None:
        self.cancelled.append(clip_id)


class FakeVolumeMonitor:
    def __init__(self, host: str) -> None:
        self.host = host
        self.volume: float | None = None
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def _player(client: FakeSonosCloudClient, *, speaker_host: str | None = None) -> SonosAudioPlayer:
    return SonosAudioPlayer(
        client=client,
        settings=SonosSettings(speaker_name="Zimmer", speaker_host=speaker_host),
    )


def test_get_volume_converts_from_the_sonos_0_100_scale() -> None:
    player = _player(FakeSonosCloudClient(volume=40))

    assert asyncio.run(player.get_volume()) == 0.4


def test_set_volume_converts_to_the_sonos_0_100_scale() -> None:
    client = FakeSonosCloudClient()
    player = _player(client)

    asyncio.run(player.set_volume(0.75))

    assert asyncio.run(player.get_volume()) == 0.75


def test_set_volume_clamps_out_of_range_values() -> None:
    client = FakeSonosCloudClient()
    player = _player(client)

    asyncio.run(player.set_volume(1.5))
    assert asyncio.run(player.get_volume()) == 1.0

    asyncio.run(player.set_volume(-0.5))
    assert asyncio.run(player.get_volume()) == 0.0


def test_wav_duration_uses_header_for_well_formed_wav() -> None:
    audio = _wav(declared_frames=24000, data_bytes=24000 * 2)
    assert _wav_duration(audio) == 1.0


def test_wav_duration_ignores_bogus_streaming_frame_count() -> None:
    # OpenAI TTS declares a placeholder frame count far larger than the payload;
    # duration must track the real bytes (~1s), not the header (which would be hours).
    audio = _wav(declared_frames=0x7FFFFFFF, data_bytes=24000 * 2)
    assert abs(_wav_duration(audio) - 1.0) < 0.01


def test_play_skips_when_already_cancelled() -> None:
    client = FakeSonosCloudClient()
    player = _player(client)
    cancel = asyncio.Event()
    cancel.set()

    asyncio.run(player.play(b"ignored", cancel=cancel))

    assert client.played == []
    assert client.cancelled == []


def test_get_volume_without_speaker_host_does_not_start_a_monitor(monkeypatch) -> None:
    monkeypatch.setattr(player_module, "SonosVolumeMonitor", FakeVolumeMonitor)
    client = FakeSonosCloudClient(volume=40)
    player = _player(client, speaker_host=None)

    assert asyncio.run(player.get_volume()) == 0.4


def test_get_volume_prefers_the_cached_monitor_value(monkeypatch) -> None:
    monkeypatch.setattr(player_module, "SonosVolumeMonitor", FakeVolumeMonitor)
    client = FakeSonosCloudClient(volume=40)
    player = _player(client, speaker_host="192.168.1.42")

    monitor = asyncio.run(player._resolve_volume_monitor())
    assert monitor is not None
    assert monitor.started
    monitor.volume = 0.9

    assert asyncio.run(player.get_volume()) == 0.9


def test_get_volume_falls_back_to_the_cloud_api_before_the_first_event(monkeypatch) -> None:
    monkeypatch.setattr(player_module, "SonosVolumeMonitor", FakeVolumeMonitor)
    client = FakeSonosCloudClient(volume=40)
    player = _player(client, speaker_host="192.168.1.42")

    assert asyncio.run(player.get_volume()) == 0.4


def test_close_stops_the_volume_monitor(monkeypatch) -> None:
    monkeypatch.setattr(player_module, "SonosVolumeMonitor", FakeVolumeMonitor)
    client = FakeSonosCloudClient()
    player = _player(client, speaker_host="192.168.1.42")

    monitor = asyncio.run(player._resolve_volume_monitor())
    assert monitor is not None
    asyncio.run(player.close())

    assert monitor.stopped
