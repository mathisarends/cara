from abc import ABC, abstractmethod
from uuid import UUID

from gateway.features.rooms.domain import Room, RoomGroup


class RoomStore(ABC):
    @abstractmethod
    def rooms(self) -> tuple[Room, ...]: ...

    @abstractmethod
    def groups(self) -> tuple[RoomGroup, ...]: ...

    @abstractmethod
    def room(self, room_id: UUID) -> Room | None: ...

    @abstractmethod
    def group(self, group_id: UUID) -> RoomGroup | None: ...


class RoomConnections(ABC):
    @abstractmethod
    def connect(self, room_id: UUID, connection_id: UUID) -> None: ...

    @abstractmethod
    def disconnect(self, room_id: UUID, connection_id: UUID) -> None: ...

    @abstractmethod
    def is_connected(self, room_id: UUID) -> bool: ...
