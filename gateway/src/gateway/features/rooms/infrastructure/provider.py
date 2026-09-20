from dishka import Provider, Scope, provide

from gateway.agent_runtime.settings import GatewaySettings
from gateway.features.rooms.application import (
    RoomConnections,
    RoomRegistryService,
    RoomStore,
)
from gateway.features.rooms.domain import Room, RoomGroup
from gateway.features.rooms.infrastructure.memory import (
    InMemoryRoomConnections,
    InMemoryRoomStore,
)


class RoomProvider(Provider):
    @provide(scope=Scope.APP)
    def store(self, settings: GatewaySettings) -> InMemoryRoomStore:
        rooms = tuple(
            Room(room_id, room.display_name) for room_id, room in settings.rooms.items()
        )
        rooms_by_id = {room.room_id: room for room in rooms}
        groups: list[RoomGroup] = []
        for group_id, group in settings.room_groups.items():
            unknown = set(group.rooms) - rooms_by_id.keys()
            if unknown:
                raise ValueError(
                    f"Room group {group_id!r} contains unknown rooms: "
                    f"{', '.join(sorted(unknown))}"
                )
            groups.append(
                RoomGroup(
                    group_id,
                    group.display_name,
                    tuple(rooms_by_id[room_id] for room_id in group.rooms),
                )
            )
        return InMemoryRoomStore(rooms, tuple(groups))

    @provide(scope=Scope.APP)
    def store_port(self, store: InMemoryRoomStore) -> RoomStore:
        return store

    @provide(scope=Scope.APP)
    def connections(self) -> InMemoryRoomConnections:
        return InMemoryRoomConnections()

    @provide(scope=Scope.APP)
    def connections_port(self, connections: InMemoryRoomConnections) -> RoomConnections:
        return connections

    @provide(scope=Scope.APP)
    def registry(
        self, store: RoomStore, connections: RoomConnections
    ) -> RoomRegistryService:
        return RoomRegistryService(store, connections)
