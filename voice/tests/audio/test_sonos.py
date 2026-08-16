import asyncio

from sonosify import ClipPriority, ClipType

import voice.audio.sonos.controller as controller_module
from voice.audio.sonos import SonosController, SonosSettings


class FakeHostedAudioClip:
    def __init__(self) -> None:
        self.finished = asyncio.Event()
        self.cancelled = False
        self.closed = False

    async def wait_until_finished(self) -> None:
        await self.finished.wait()

    async def cancel(self) -> None:
        self.cancelled = True

    def close(self) -> None:
        self.closed = True


class FakeSonosClient:
    ip = "192.168.1.42"

    def __init__(self, volume: int = 50) -> None:
        self._volume = volume
        self.clip = FakeHostedAudioClip()
        self.played: list[tuple[bytes, dict[str, object]]] = []
        self.closed = False

    async def play_audio_clip_data(
        self, audio: bytes, **kwargs: object
    ) -> FakeHostedAudioClip:
        self.played.append((audio, kwargs))
        return self.clip

    async def get_volume(self) -> int:
        return self._volume

    async def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, volume))

    async def close(self) -> None:
        self.closed = True


def _controller(client: FakeSonosClient) -> SonosController:
    return SonosController(client=client, settings=SonosSettings(speaker_name="Zimmer"))


def test_get_volume_converts_from_the_sonos_0_100_scale() -> None:
    controller = _controller(FakeSonosClient(volume=40))

    assert asyncio.run(controller.get_volume()) == 0.4


def test_set_volume_converts_to_the_sonos_0_100_scale() -> None:
    client = FakeSonosClient()
    controller = _controller(client)

    asyncio.run(controller.set_volume(0.75))

    assert asyncio.run(controller.get_volume()) == 0.75


def test_set_volume_clamps_out_of_range_values() -> None:
    client = FakeSonosClient()
    controller = _controller(client)

    asyncio.run(controller.set_volume(1.5))
    assert asyncio.run(controller.get_volume()) == 1.0

    asyncio.run(controller.set_volume(-0.5))
    assert asyncio.run(controller.get_volume()) == 0.0


def test_play_uses_sonosifys_hosted_clip_api() -> None:
    async def run() -> tuple[FakeSonosClient, FakeHostedAudioClip]:
        client = FakeSonosClient()
        controller = _controller(client)
        play = asyncio.create_task(controller.play(b"wav-data"))
        await asyncio.sleep(0)
        client.clip.finished.set()
        await play
        return client, client.clip

    client, clip = asyncio.run(run())

    assert client.played == [
        (
            b"wav-data",
            {
                "local_host": None,
                "app_id": "cara",
                "name": "Cara",
                "priority": ClipPriority.HIGH,
                "clip_type": ClipType.CUSTOM,
            },
        )
    ]
    assert clip.closed


def test_play_cancels_a_running_hosted_clip() -> None:
    async def run() -> FakeHostedAudioClip:
        client = FakeSonosClient()
        controller = _controller(client)
        cancel = asyncio.Event()
        play = asyncio.create_task(controller.play(b"wav-data", cancel=cancel))
        await asyncio.sleep(0)
        cancel.set()
        await play
        return client.clip

    clip = asyncio.run(run())

    assert clip.cancelled
    assert clip.closed


def test_play_skips_when_already_cancelled() -> None:
    client = FakeSonosClient()
    controller = _controller(client)
    cancel = asyncio.Event()
    cancel.set()

    asyncio.run(controller.play(b"ignored", cancel=cancel))

    assert client.played == []


def test_close_leaves_an_injected_client_open() -> None:
    client = FakeSonosClient()
    controller = _controller(client)

    asyncio.run(controller.close())

    assert not client.closed


def test_controller_resolves_and_owns_a_local_client(monkeypatch) -> None:
    client = FakeSonosClient(volume=40)

    class FakeController:
        async def client(self, room: str | None, *, ip: str | None) -> FakeSonosClient:
            assert room == "Zimmer"
            assert ip == "192.168.1.42"
            return client

    monkeypatch.setattr(controller_module, "SonosifyController", FakeController)
    controller = SonosController(
        settings=SonosSettings(
            speaker_name="Zimmer",
            ip_address="192.168.1.42",
        )
    )

    assert asyncio.run(controller.get_volume()) == 0.4
    asyncio.run(controller.close())

    assert client.closed
