import asyncio

from cara.audio.sonos import SonosAudioPlayer, SonosSettings


class FakePlayer:
    def __init__(self, player_id: str) -> None:
        self.id = player_id


class FakeVolumeState:
    def __init__(self, volume: int) -> None:
        self.volume = volume


class FakeSonosCloudClient:
    def __init__(self, volume: int = 50) -> None:
        self._volume = volume

    async def resolve_player(self, name: str) -> FakePlayer:
        return FakePlayer("RINCON_TEST")

    async def get_player_volume(self, player_id: str) -> FakeVolumeState:
        return FakeVolumeState(self._volume)

    async def set_player_volume(self, player_id: str, *, volume: int) -> None:
        self._volume = max(0, min(100, volume))


def _player(client: FakeSonosCloudClient) -> SonosAudioPlayer:
    return SonosAudioPlayer(client=client, settings=SonosSettings(speaker_name="Zimmer"))


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
