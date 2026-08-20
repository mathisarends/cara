from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from gateway.presentation.protocol import GatewayProtocol

type RpcHandler = Callable[[Any], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class RpcMethodBinding:
    name: str
    handler: RpcHandler


class GatewayRpcMethods:
    def __init__(
        self,
        protocol: GatewayProtocol,
        bindings: Iterable[RpcMethodBinding],
    ) -> None:
        self._protocol = protocol
        self._handlers = _handlers_by_name(bindings)
        declared = {method.name for method in protocol.methods}
        bound = set(self._handlers)
        if declared != bound:
            missing = sorted(declared - bound)
            unexpected = sorted(bound - declared)
            raise ValueError(
                "RPC bindings do not match the protocol: "
                f"missing={missing}, unexpected={unexpected}"
            )

    def parse_request(self, raw_request: object) -> BaseModel:
        return self._protocol.parse_request(raw_request)

    async def execute(self, request: BaseModel) -> Any:
        method = request.model_dump()["method"]
        return await self._handlers[str(method)](request)


def _handlers_by_name(
    bindings: Iterable[RpcMethodBinding],
) -> dict[str, RpcHandler]:
    handlers: dict[str, RpcHandler] = {}
    for binding in bindings:
        if binding.name in handlers:
            raise ValueError(f"Duplicate RPC binding: {binding.name}")
        handlers[binding.name] = binding.handler
    return handlers
