import asyncio

from room.features.room.application.ports import RoomConnection
from room.features.room.domain import DeviceStatus, Room, RoomState


class ReportingService:
    def __init__(self, room: Room) -> None:
        self._room = room
        self._room_connection: RoomConnection | None = None
        self._connection_lock = asyncio.Lock()

    async def attach(self, room_connection: RoomConnection) -> None:
        async with self._connection_lock:
            self._room_connection = room_connection
            await room_connection.report_state(self._room.state)
            for device in self._room.devices:
                await room_connection.report_device(device.device_id, device.status)
            if self._room.volume is not None:
                await room_connection.report_volume(self._room.volume)

    async def detach(self, room_connection: RoomConnection) -> None:
        async with self._connection_lock:
            if self._room_connection is room_connection:
                self._room_connection = None

    async def report_state(self, state: RoomState) -> None:
        self._room.change_state(state)
        room_connection = self._room_connection
        if room_connection is not None:
            await room_connection.report_state(state)

    async def report_device(self, device_id: str, status: DeviceStatus) -> None:
        device = self._room.device(device_id)
        device.report_status(status)
        room_connection = self._room_connection
        if room_connection is not None:
            await room_connection.report_device(device_id, status)

    async def report_volume(self, volume: int) -> None:
        self._room.report_volume(volume)
        room_connection = self._room_connection
        if room_connection is not None:
            await room_connection.report_volume(volume)
