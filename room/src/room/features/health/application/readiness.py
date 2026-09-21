from dataclasses import dataclass

from room.features.health.domain import RoomNotReadyError


@dataclass(frozen=True, slots=True)
class ReadinessSnapshot:
    config_loaded: bool
    devices_initialized: bool
    gateway_registered: bool
    gateway_connected: bool
    voice_ready: bool

    @property
    def ready(self) -> bool:
        return (
            self.config_loaded
            and self.devices_initialized
            and self.gateway_registered
            and self.gateway_connected
            and self.voice_ready
        )

    @property
    def missing(self) -> tuple[str, ...]:
        conditions = (
            ("config_loaded", self.config_loaded),
            ("devices_initialized", self.devices_initialized),
            ("gateway_registered", self.gateway_registered),
            ("gateway_connected", self.gateway_connected),
            ("voice_ready", self.voice_ready),
        )
        return tuple(name for name, satisfied in conditions if not satisfied)


class ReadinessService:
    def __init__(self) -> None:
        self._config_loaded = False
        self._devices_initialized = False
        self._gateway_registered = False
        self._gateway_connected = False
        self._voice_ready = False

    def config_loaded(self) -> None:
        self._config_loaded = True

    def devices_initialized(self) -> None:
        self._devices_initialized = True

    def gateway_registered(self, registered: bool) -> None:
        self._gateway_registered = registered

    def gateway_connected(self, connected: bool) -> None:
        self._gateway_connected = connected

    def voice_ready(self, ready: bool) -> None:
        self._voice_ready = ready

    def snapshot(self) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            config_loaded=self._config_loaded,
            devices_initialized=self._devices_initialized,
            gateway_registered=self._gateway_registered,
            gateway_connected=self._gateway_connected,
            voice_ready=self._voice_ready,
        )

    def require_ready(self) -> ReadinessSnapshot:
        snapshot = self.snapshot()
        if snapshot.ready:
            return snapshot
        missing = ", ".join(snapshot.missing)
        raise RoomNotReadyError(f"Room is not ready: {missing}")
