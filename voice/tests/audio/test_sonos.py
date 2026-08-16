import asyncio
import io
import wave

from sonosify import ClipPriority, ClipType

import voice.audio.output.sonos as sonos_module
from voice.audio.output.sonos import SonosOutput, SonosSettings


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


def _output(client: FakeSonosClient) -> SonosOutput:
    return SonosOutput(client=client, settings=SonosSettings(speaker_name="Zimmer"))


def test_get_volume_converts_from_the_sonos_0_100_scale() -> None:
    output = _output(FakeSonosClient(volume=40))

    assert asyncio.run(output.get_volume()) == 0.4


def test_set_volume_converts_to_the_sonos_0_100_scale() -> None:
    client = FakeSonosClient()
    output = _output(client)

    asyncio.run(output.set_volume(0.75))

    assert asyncio.run(output.get_volume()) == 0.75


def test_set_volume_clamps_out_of_range_values() -> None:
    client = FakeSonosClient()
    output = _output(client)

    asyncio.run(output.set_volume(1.5))
    assert asyncio.run(output.get_volume()) == 1.0

    asyncio.run(output.set_volume(-0.5))
    assert asyncio.run(output.get_volume()) == 0.0


def test_finish_response_uses_sonosifys_hosted_clip_api() -> None:
    async def run() -> tuple[FakeSonosClient, FakeHostedAudioClip]:
        client = FakeSonosClient()
        output = _output(client)
        await output.start(sample_rate=16_000, channels=1)
        await output.play_chunk(b"\x01\x00\x02\x00")
        finish = asyncio.create_task(output.finish_response())
        await asyncio.sleep(0)
        client.clip.finished.set()
        await finish
        return client, client.clip

    client, clip = asyncio.run(run())
    audio, options = client.played[0]
    with wave.open(io.BytesIO(audio), "rb") as wav_file:
        assert wav_file.getframerate() == 16_000
        assert wav_file.getnchannels() == 1
        assert wav_file.readframes(wav_file.getnframes()) == b"\x01\x00\x02\x00"
    assert options == {
        "local_host": None,
        "app_id": "cara",
        "name": "Cara",
        "priority": ClipPriority.HIGH,
        "clip_type": ClipType.CUSTOM,
    }
    assert clip.closed


def test_clear_buffer_cancels_a_running_hosted_clip() -> None:
    async def run() -> FakeHostedAudioClip:
        client = FakeSonosClient()
        output = _output(client)
        await output.start(sample_rate=16_000, channels=1)
        await output.play_chunk(b"\x00\x00")
        finish = asyncio.create_task(output.finish_response())
        await asyncio.sleep(0)
        await output.clear_buffer()
        await asyncio.gather(finish, return_exceptions=True)
        return client.clip

    clip = asyncio.run(run())

    assert clip.cancelled
    assert clip.closed


def test_stop_leaves_an_injected_client_open() -> None:
    client = FakeSonosClient()
    output = _output(client)

    asyncio.run(output.stop())

    assert not client.closed


def test_output_resolves_and_owns_a_local_client(monkeypatch) -> None:
    client = FakeSonosClient(volume=40)

    class FakeController:
        async def client(self, room: str | None, *, ip: str | None) -> FakeSonosClient:
            assert room == "Zimmer"
            assert ip == "192.168.1.42"
            return client

    monkeypatch.setattr(sonos_module, "SonosifyController", FakeController)
    output = SonosOutput(
        settings=SonosSettings(
            speaker_name="Zimmer",
            ip_address="192.168.1.42",
        )
    )

    assert asyncio.run(output.get_volume()) == 0.4
    asyncio.run(output.stop())

    assert client.closed
