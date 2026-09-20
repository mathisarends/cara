import asyncio

from room.features.room.application.ports import RoomConnection
from room.features.room.domain import DeviceStatus, Room, RoomState


class ReportingService:
    def __init__(self, room: Room) -> None:
        self._room = room
        self._connection: RoomConnection | None = None
        self._lock = asyncio.Lock()

    async def attach(self, connection: RoomConnection) -> None:
        async with self._lock:
            self._connection = connection
            await connection.report_state(self._room.state)
            for device in self._room.devices:
                await connection.report_device(device.device_id, device.status)
            if self._room.volume is not None:
                await connection.report_volume(self._room.volume)

    async def detach(self, connection: RoomConnection) -> None:
        async with self._lock:
            if self._connection is connection:
                self._connection = None

    async def report_state(self, state: RoomState) -> None:
        self._room.change_state(state)
        connection = self._connection
        if connection is not None:
            await connection.report_state(state)

    async def report_device(self, device_id: str, status: DeviceStatus) -> None:
        device = self._room.device(device_id)
        device.report_status(status)
        connection = self._connection
        if connection is not None:
            await connection.report_device(device_id, status)

    async def report_volume(self, volume: int) -> None:
        self._room.report_volume(volume)
        connection = self._connection
        if connection is not None:
            await connection.report_volume(volume)
