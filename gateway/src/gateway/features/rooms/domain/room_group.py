from uuid import UUID

from gateway.features.rooms.domain.room import Room
from gateway.shared import Aggregate


class RoomGroup(Aggregate):
    def __init__(
        self,
        group_id: UUID,
        display_name: str,
        rooms: tuple[Room, ...],
    ) -> None:
        super().__init__(id=group_id)
        self._display_name = display_name
        self._rooms = rooms

    @property
    def group_id(self) -> UUID:
        return self.id

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def rooms(self) -> tuple[Room, ...]:
        return self._rooms
