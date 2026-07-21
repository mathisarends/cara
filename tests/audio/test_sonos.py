import asyncio

from cara.audio.sonos import SonosAudioPlayer


class FakeSoCoDevice:
    def __init__(self, volume: int = 50) -> None:
        self.volume = volume


def test_get_volume_converts_from_the_sonos_0_100_scale() -> None:
    player = SonosAudioPlayer(device=FakeSoCoDevice(volume=40))

    assert asyncio.run(player.get_volume()) == 0.4


def test_set_volume_converts_to_the_sonos_0_100_scale() -> None:
    device = FakeSoCoDevice()
    player = SonosAudioPlayer(device=device)

    asyncio.run(player.set_volume(0.75))

    assert device.volume == 75


def test_set_volume_clamps_out_of_range_values() -> None:
    device = FakeSoCoDevice()
    player = SonosAudioPlayer(device=device)

    asyncio.run(player.set_volume(1.5))
    assert device.volume == 100

    asyncio.run(player.set_volume(-0.5))
    assert device.volume == 0
