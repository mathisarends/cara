from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from gateway.presentation.protocol import (
    GatewayProtocol,
    RpcMethodDefinition,
    RpcRequestEnvelope,
)
from gateway.presentation.rpc_decorators import method_metadata


@dataclass(frozen=True, slots=True)
class RpcInvocation:
    request: RpcRequestEnvelope
    method: RpcMethodDefinition
    params: BaseModel


class RpcInvalidParamsError(Exception):
    def __init__(self, error: ValidationError) -> None:
        issue = error.errors(include_url=False)[0]
        location = ".".join(str(part) for part in ("params", *issue["loc"]))
        self.message = f"Invalid params at {location}: {issue['msg']}"
        super().__init__(self.message)


class GatewayRpcMethods:
    def __init__(
        self,
        protocol: GatewayProtocol,
        handlers: Iterable[Any],
    ) -> None:
        self._protocol = protocol
        self._handlers = _handlers_by_name(handlers)
        declared = {method.name for method in protocol.methods}
        bound = set(self._handlers)
        if declared != bound:
            missing = sorted(declared - bound)
            unexpected = sorted(bound - declared)
            raise ValueError(
                "RPC handlers do not match the protocol: "
                f"missing={missing}, unexpected={unexpected}"
            )

    def parse_request(self, raw_request: object) -> RpcInvocation:
        request = RpcRequestEnvelope.model_validate(raw_request)
        method = self._protocol.method(request.method)
        try:
            params = TypeAdapter(method.params).validate_python(request.params)
        except ValidationError as error:
            raise RpcInvalidParamsError(error) from error
        return RpcInvocation(request=request, method=method, params=params)

    async def execute(self, invocation: RpcInvocation) -> Any:
        return await self._handlers[invocation.method.name](invocation.params)


def _handlers_by_name(handlers: Iterable[Any]) -> dict[str, Any]:
    by_name: dict[str, Any] = {}
    for owner in handlers:
        for attribute_name, function in vars(type(owner)).items():
            metadata = method_metadata(function)
            if metadata is None:
                continue
            if metadata.name in by_name:
                raise ValueError(f"Duplicate RPC handler: {metadata.name}")
            by_name[metadata.name] = getattr(owner, attribute_name)
    return by_name
