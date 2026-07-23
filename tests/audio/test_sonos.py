import asyncio

from cara.audio.sonos import SonosAudioPlayer


class FakeSonosClient:
    def __init__(self, volume: int = 50) -> None:
        self._volume = volume

    async def get_volume(self) -> int:
        return self._volume

    async def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, volume))


def test_get_volume_converts_from_the_sonos_0_100_scale() -> None:
    player = SonosAudioPlayer(client=FakeSonosClient(volume=40))

    assert asyncio.run(player.get_volume()) == 0.4


def test_set_volume_converts_to_the_sonos_0_100_scale() -> None:
    client = FakeSonosClient()
    player = SonosAudioPlayer(client=client)

    asyncio.run(player.set_volume(0.75))

    assert asyncio.run(player.get_volume()) == 0.75


def test_set_volume_clamps_out_of_range_values() -> None:
    client = FakeSonosClient()
    player = SonosAudioPlayer(client=client)

    asyncio.run(player.set_volume(1.5))
    assert asyncio.run(player.get_volume()) == 1.0

    asyncio.run(player.set_volume(-0.5))
    assert asyncio.run(player.get_volume()) == 0.0
