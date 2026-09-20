from room.features.room.domain.values import Capability, DeviceKind, DeviceStatus


class Device:
    def __init__(
        self,
        device_id: str,
        kind: DeviceKind,
        capabilities: frozenset[Capability],
    ) -> None:
        if not device_id:
            raise ValueError("device_id must not be empty")
        if not capabilities:
            raise ValueError("A device must provide at least one capability")
        self._device_id = device_id
        self._kind = kind
        self._capabilities = capabilities
        self._status = DeviceStatus.AVAILABLE

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
