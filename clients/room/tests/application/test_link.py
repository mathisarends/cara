import asyncio
from uuid import uuid4

from room.features.health.application import ReadinessService
from room.features.room.application import (
    GatewayLink,
    GatewayRegistry,
    RegistrationService,
    ReportingService,
    RoomConnection,
    RoomConnector,
)
from room.features.room.domain import (
    Capability,
    Device,
    DeviceKind,
    DeviceStatus,
    Room,
    RoomState,
)


class _Registry(GatewayRegistry):
    def __init__(self) -> None:
        self.registrations = 0

    async def register(self, room: Room) -> None:
        self.registrations += 1


class _Connection(RoomConnection):
    def __init__(self) -> None:
        self.states: list[RoomState] = []
        self.devices: list[tuple[str, DeviceStatus]] = []
        self.closed = False

    async def report_state(self, state: RoomState) -> None:
        self.states.append(state)

    async def report_device(self, device_id: str, status: DeviceStatus) -> None:
        self.devices.append((device_id, status))

    async def report_volume(self, volume: int) -> None:
        pass

    async def wait_closed(self) -> None:
        return

    async def close(self) -> None:
        self.closed = True


class _Connector(RoomConnector):
    def __init__(self, connections: tuple[_Connection, ...]) -> None:
        self._connections = iter(connections)

    async def connect(self) -> RoomConnection:
        return next(self._connections)


async def test_reconnects_with_registration_and_reports_snapshot() -> None:
    device = Device(
        "microphone",
        DeviceKind.MICROPHONE,
        frozenset({Capability.AUDIO_INPUT}),
    )
    room = Room(uuid4(), (device,))
    registry = _Registry()
    first = _Connection()
    second = _Connection()
    connector = _Connector((first, second))
    readiness = ReadinessService()
    reporting = ReportingService(room)
    registration = RegistrationService(room, registry, readiness)
    link = GatewayLink(
        room,
        registration,
        connector,
        reporting,
        readiness,
        initial_retry_seconds=0,
        maximum_retry_seconds=0,
    )

    task = asyncio.create_task(link.run())
    while registry.registrations < 2:
        await asyncio.sleep(0)
    link.stop()
    await task

    assert registry.registrations == 2
    assert first.states == [RoomState.IDLE]
    assert second.states == [RoomState.IDLE]
    expected_device = [("microphone", DeviceStatus.AVAILABLE)]
    assert first.devices == expected_device
    assert second.devices == expected_device
    assert first.closed
    assert second.closed
