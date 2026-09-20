from abc import ABC, abstractmethod
from types import TracebackType

from room.features.room.domain import DeviceStatus, Room, RoomState


class GatewayRegistry(ABC):
    @abstractmethod
    async def register(self, room: Room) -> None: ...


class RoomConnection(ABC):
    @abstractmethod
    async def report_state(self, state: RoomState) -> None: ...

    @abstractmethod
    async def report_device(self, device_id: str, status: DeviceStatus) -> None: ...

    @abstractmethod
    async def report_volume(self, volume: int) -> None: ...

    @abstractmethod
    async def wait_closed(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    async def __aenter__(self) -> "RoomConnection":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()


class RoomConnector(ABC):
    @abstractmethod
    async def connect(self) -> RoomConnection: ...
