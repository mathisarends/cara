import asyncio
from typing import cast

import pytest
from sonosify import (
    AudioClip,
    ClipLEDBehavior,
    ClipPriority,
    ClipStatus,
    ClipType,
    SonosClient,
    streaming_wav_header,
)

from voice.audio.output.sonos import SonosOutput
from voice.sonos import SonosSettings

_SAMPLE_RATE = 16_000
_HEADER = streaming_wav_header(_SAMPLE_RATE, 1, 2)


class FakeAudioClipStream:
    def __init__(self, status: ClipStatus = ClipStatus.DONE) -> None:
        self.written = bytearray()
        self.ended = False
        self.aborted = False
        self.closed = False
        self.fetched = True
        self.finished = asyncio.Event()
        self.status = status

    async def write(self, data: bytes) -> None:
        self.written.extend(data)

    async def end(self) -> None:
        self.ended = True

    async def abort(self) -> None:
        self.aborted = True

    def close(self) -> None:
        self.closed = True

    async def wait_until_finished(self) -> AudioClip:
        await self.finished.wait()
        return AudioClip(
            id="clip-id",
            name="Cara",
            app_id="cara",
            status=self.status,
        )


class FakeSonosClient:
    ip = "192.168.1.42"

    def __init__(self, volume: int = 30) -> None:
        self.stream = FakeAudioClipStream()
        self.opened: list[dict[str, object]] = []
        self.closed = False
        self.volume = volume

    async def get_volume(self) -> int:
        return self.volume

    async def stream_audio_clip(self, **kwargs: object) -> FakeAudioClipStream:
        self.opened.append(kwargs)
        return self.stream

    async def close(self) -> None:
        self.closed = True


def _output(client: FakeSonosClient) -> SonosOutput:
    return SonosOutput(
        client=cast(SonosClient, client),
        settings=SonosSettings(ip_address=client.ip),
    )


def test_start_opens_a_streaming_clip_and_writes_a_wav_header() -> None:
    async def run() -> FakeSonosClient:
        client = FakeSonosClient()
        await _output(client).start(sample_rate=_SAMPLE_RATE, channels=1)
        return client

    client = asyncio.run(run())

    assert client.opened == [
        {
            "local_host": None,
            "app_id": "cara",
            "name": "Cara",
            "volume": 45,
            "priority": ClipPriority.HIGH,
            "clip_type": ClipType.CUSTOM,
            "led_behavior": ClipLEDBehavior.WHITE_LED_QUICK_BREATHING,
            # 1.5s of head start at 16 kHz mono 16-bit
            "prebuffer_bytes": 48_000,
        }
    ]
    assert bytes(client.stream.written) == _HEADER


def test_play_chunk_reaches_the_speaker_before_the_response_finishes() -> None:
    async def run() -> FakeAudioClipStream:
        client = FakeSonosClient()
        output = _output(client)
        await output.start(sample_rate=_SAMPLE_RATE, channels=1)
        await output.play_chunk(b"\x01\x00\x02\x00")
        return client.stream

    stream = asyncio.run(run())

    assert bytes(stream.written) == _HEADER + b"\x01\x00\x02\x00"
    assert not stream.ended


def test_finish_response_pads_short_responses_and_ends_the_stream() -> None:
    async def run() -> FakeAudioClipStream:
        client = FakeSonosClient()
        output = _output(client)
        await output.start(sample_rate=_SAMPLE_RATE, channels=1)
        await output.play_chunk(b"\x01\x00\x02\x00")
        finish = asyncio.create_task(output.finish_response())
        await asyncio.sleep(0)
        client.stream.finished.set()
        await finish
        return client.stream

    stream = asyncio.run(run())

    pcm = bytes(stream.written)[len(_HEADER) :]
    assert len(pcm) == 48_000
    assert pcm[:4] == b"\x01\x00\x02\x00"
    assert pcm[4:] == bytes(47_996)
    assert stream.ended
    assert stream.closed
    assert not stream.aborted


def test_finish_response_leaves_long_responses_unpadded() -> None:
    async def run() -> FakeAudioClipStream:
        client = FakeSonosClient()
        output = _output(client)
        await output.start(sample_rate=_SAMPLE_RATE, channels=1)
        await output.play_chunk(bytes(60_000))
        finish = asyncio.create_task(output.finish_response())
        await asyncio.sleep(0)
        client.stream.finished.set()
        await finish
        return client.stream

    stream = asyncio.run(run())

    assert len(bytes(stream.written)) == len(_HEADER) + 60_000


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
            settings=SonosSettings(ip_address=client.ip, clip_volume_boost=boost),
        )
        await output.start(sample_rate=_SAMPLE_RATE, channels=1)
        return client

    client = asyncio.run(run())

    assert client.opened[0]["volume"] == expected


def test_prebuffer_is_configurable() -> None:
    async def run() -> FakeSonosClient:
        client = FakeSonosClient()
        output = SonosOutput(
            client=cast(SonosClient, client),
            settings=SonosSettings(
                ip_address=client.ip,
                clip_prebuffer_seconds=0.25,
            ),
        )
        await output.start(sample_rate=_SAMPLE_RATE, channels=1)
        return client

    client = asyncio.run(run())

    assert client.opened[0]["prebuffer_bytes"] == 8_000


def test_clear_buffer_aborts_a_running_stream() -> None:
    async def run() -> FakeAudioClipStream:
        client = FakeSonosClient()
        output = _output(client)
        await output.start(sample_rate=_SAMPLE_RATE, channels=1)
        await output.play_chunk(b"\x00\x00")
        finish = asyncio.create_task(output.finish_response())
        await asyncio.sleep(0)
        await output.clear_buffer()
        await asyncio.gather(finish, return_exceptions=True)
        return client.stream

    stream = asyncio.run(run())

    assert stream.aborted
    assert stream.closed


def test_finish_response_without_audio_discards_the_stream() -> None:
    async def run() -> FakeAudioClipStream:
        client = FakeSonosClient()
        output = _output(client)
        await output.start(sample_rate=_SAMPLE_RATE, channels=1)
        await output.finish_response()
        return client.stream

    stream = asyncio.run(run())

    assert stream.aborted
    assert not stream.ended


def test_finish_response_fails_when_sonos_rejects_clip() -> None:
    client = FakeSonosClient()
    client.stream = FakeAudioClipStream(ClipStatus.ERROR)
    client.stream.finished.set()
    output = _output(client)

    async def run() -> None:
        await output.start(sample_rate=_SAMPLE_RATE, channels=1)
        await output.play_chunk(b"\x00\x00")
        await output.finish_response()

    with pytest.raises(RuntimeError, match="audio clip was not played"):
        asyncio.run(run())

    assert len(client.opened) == 1


def test_stop_leaves_an_injected_client_open() -> None:
    client = FakeSonosClient()
    output = _output(client)

    asyncio.run(output.stop())

    assert not client.closed
