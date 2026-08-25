from pydantic import TypeAdapter

from gateway.features.automation.domain import AutomationEnvelope


class AutomationEnvelopeCodec:
    def __init__(self) -> None:
        self._adapter = TypeAdapter(AutomationEnvelope)

    def encode(self, value: AutomationEnvelope) -> str:
        return self._adapter.dump_json(value).decode()

    def decode(self, value: str) -> AutomationEnvelope:
        return self._adapter.validate_json(value)
