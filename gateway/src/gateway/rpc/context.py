from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GatewaySocketSession:
    connection_id: UUID


@dataclass(frozen=True, slots=True)
class RoomSocketSession:
    connection_id: UUID
    room_id: UUID
