from gateway.features.rooms.domain.values import Capability, DeviceKind, DeviceStatus
from gateway.shared import Entity


class Device(Entity):
    def __init__(
        self,
        device_id: str,
        kind: DeviceKind,
        capabilities: frozenset[Capability],
        status: DeviceStatus = DeviceStatus.AVAILABLE,
    ) -> None:
        super().__init__()
        self._device_id = device_id
        self._kind = kind
        self._capabilities = capabilities
        self._status = status

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def kind(self) -> DeviceKind:
        return self._kind

    @property
    def capabilities(self) -> frozenset[Capability]:
        return self._capabilities

    @property
    def status(self) -> DeviceStatus:
        return self._status

    def report_status(self, status: DeviceStatus) -> None:
        self._status = status
