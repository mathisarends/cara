from dishka import Provider, Scope, provide

from room.platform.settings import RoomConfig


class PlatformProvider(Provider):
    def __init__(self, config: RoomConfig) -> None:
        super().__init__()
        self._config = config

    @provide(scope=Scope.APP)
    def config(self) -> RoomConfig:
        return self._config
