from dishka import Provider, Scope, provide

from room.platform.settings import RoomConfig
from voice import VoiceSessionConfig


class PlatformProvider(Provider):
    def __init__(
        self,
        room_config: RoomConfig,
        voice_config: VoiceSessionConfig | None,
    ) -> None:
        super().__init__()
        self._room_config = room_config
        self._voice_config = voice_config

    @provide(scope=Scope.APP)
    def room_config(self) -> RoomConfig:
        return self._room_config

    @provide(scope=Scope.APP)
    def voice_config(self) -> VoiceSessionConfig | None:
        return self._voice_config
