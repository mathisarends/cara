import asyncio
import io
import wave
from typing import cast

import pytest
from sonosify import (
    AudioClip,
    ClipLEDBehavior,
    ClipPriority,
    ClipStatus,
    ClipType,
    SonosClient,
)

import voice.audio.output.sonos as sonos_module
from voice.audio.output.sonos import SonosOutput
from voice.sonos import SonosSettings


class FakeHostedAudioClip:
    def __init__(self, status: ClipStatus = ClipStatus.DONE) -> None:
        self.finished = asyncio.Event()
        self.cancelled = False
        self.closed = False
        self.status = status
        self.fetched = True

    async def wait_until_finished(self) -> AudioClip:
        await self.finished.wait()
        return AudioClip(
            id="clip-id",
            name="Cara",
            app_id="cara",
            status=self.status,
        )

    async def cancel(self) -> None:
        self.cancelled = True

    def close(self) -> None:
        self.closed = True


class FakeSonosClient:
    ip = "192.168.1.42"

    def __init__(self, volume: int = 30) -> None:
        self.clip = FakeHostedAudioClip()
        self.played: list[tuple[bytes, dict[str, object]]] = []
        self.closed = False
        self.volume = volume

    async def get_volume(self) -> int:
        return self.volume

    async def play_audio_clip_data(
        self, audio: bytes, **kwargs: object
    ) -> FakeHostedAudioClip:
        self.played.append((audio, kwargs))
        return self.clip

    async def close(self) -> None:
        self.closed = True


def _output(client: FakeSonosClient) -> SonosOutput:
    return SonosOutput(
        client=cast(SonosClient, client),
        settings=SonosSettings(speaker_name="Zimmer"),
    )


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
        assert wav_file.getnframes() == 24_000
        pcm = wav_file.readframes(wav_file.getnframes())
        assert pcm[:4] == b"\x01\x00\x02\x00"
        assert pcm[4:] == bytes(47_996)
    assert options == {
        "local_host": None,
        "app_id": "cara",
        "name": "Cara",
        "volume": 45,
        "priority": ClipPriority.HIGH,
        "clip_type": ClipType.CUSTOM,
        "led_behavior": ClipLEDBehavior.WHITE_LED_QUICK_BREATHING,
    }
    assert clip.closed


@pytest.mark.parametrize(
    ("speaker_volume", "boost", "expected"),
    [(30, 15, 45), (95, 15, 100), (30, 0, None)],
)
def test_clips_play_above_the_speakers_own_volume(
    speaker_volume: int, boost: int, expected: int | None
) -> None:
    async def run() -> FakeSonosClient:
        client = FakeSonosClient(volume=speaker_volume)
        output = SonosOutput(
            client=cast(SonosClient, client),
            settings=SonosSettings(speaker_name="Zimmer", clip_volume_boost=boost),
        )
        await output.start(sample_rate=16_000, channels=1)
        await output.play_chunk(b"\x01\x00")
        finish = asyncio.create_task(output.finish_response())
        await asyncio.sleep(0)
        client.clip.finished.set()
        await finish
        return client

    client = asyncio.run(run())

    assert client.played[0][1]["volume"] == expected


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


def test_finish_response_fails_when_sonos_rejects_clip() -> None:
    client = FakeSonosClient()
    client.clip = FakeHostedAudioClip(ClipStatus.ERROR)
    client.clip.finished.set()
    output = _output(client)

    async def run() -> None:
        await output.start(sample_rate=16_000, channels=1)
        await output.play_chunk(b"\x00\x00")
        await output.finish_response()

    with pytest.raises(RuntimeError, match="audio clip was not played"):
        asyncio.run(run())

    assert len(client.played) == 1


def test_stop_leaves_an_injected_client_open() -> None:
    client = FakeSonosClient()
    output = _output(client)

    asyncio.run(output.stop())

    assert not client.closed


def test_output_resolves_and_owns_a_local_client(monkeypatch) -> None:
    client = FakeSonosClient()

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

    async def run() -> None:
        await output.start(sample_rate=16_000, channels=1)
        await output.stop()

    asyncio.run(run())

    assert client.closed
