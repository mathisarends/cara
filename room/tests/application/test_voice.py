import asyncio

from room.features.health.application import ReadinessService
from room.features.voice.application import RoomVoiceService
from voice import VoiceSessionConfig


class _VoiceSession:
    def __init__(self) -> None:
        self._closed = asyncio.Event()

    async def run(self) -> None:
        await self._closed.wait()

    async def wait_started(self) -> None:
        await asyncio.sleep(0)

    async def close(self) -> None:
        self._closed.set()


class _VoiceSessionFactory:
    session = _VoiceSession()

    def __init__(self, *_: object, **__: object) -> None:
        pass

    async def create(self) -> _VoiceSession:
        return self.session


async def test_voice_service_tracks_readiness_and_stops_idempotently(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "room.features.voice.application.service.VoiceSessionFactory",
        _VoiceSessionFactory,
    )
    voice_config = VoiceSessionConfig.model_validate(
        {
            "gateway": {"token": "test-token"},
            "activation": {"wake_word": {"enabled": False}},
            "barge_in": {"type": "disabled"},
        }
    )
    readiness_service = ReadinessService()
    room_voice_service = RoomVoiceService(voice_config, readiness_service)

    service_task = asyncio.create_task(room_voice_service.run())
    while not readiness_service.snapshot().voice_ready:
        await asyncio.sleep(0)

    await room_voice_service.stop()
    await room_voice_service.stop()
    await service_task

    assert readiness_service.snapshot().voice_ready is False
