from dishka import Provider, Scope, provide

from room.platform.settings import RoomConfig


class PlatformProvider(Provider):
    def __init__(self, room_config: RoomConfig) -> None:
        super().__init__()
        self._room_config = room_config

    @provide(scope=Scope.APP)
    def room_config(self) -> RoomConfig:
        return self._room_config
