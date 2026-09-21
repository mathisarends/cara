from dishka import Provider, Scope, provide

from room.features.health.application import ReadinessService
from room.features.voice.application import RoomVoiceService
from voice import VoiceSessionConfig


class VoiceProvider(Provider):
    @provide(scope=Scope.APP)
    def room_voice_service(
        self,
        voice_config: VoiceSessionConfig | None,
        readiness_service: ReadinessService,
    ) -> RoomVoiceService:
        return RoomVoiceService(voice_config, readiness_service)
