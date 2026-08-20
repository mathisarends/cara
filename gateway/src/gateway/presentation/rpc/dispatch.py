from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from pydantic import BaseModel, TypeAdapter, ValidationError

from gateway.presentation.rpc.decorators import RpcHandler, decorated_methods
from gateway.presentation.rpc.envelopes import RpcRequestEnvelope
from gateway.presentation.rpc.protocol import GatewayProtocol, RpcMethodDefinition

type BoundRpcMethod = Callable[[BaseModel], Awaitable[BaseModel | None]]


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
        handlers: Iterable[RpcHandler],
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

    async def execute(self, invocation: RpcInvocation) -> BaseModel | None:
        return await self._handlers[invocation.method.name](invocation.params)


def _handlers_by_name(handlers: Iterable[RpcHandler]) -> dict[str, BoundRpcMethod]:
    by_name: dict[str, BoundRpcMethod] = {}
    for owner in handlers:
        for decorated in decorated_methods(type(owner)):
            name = decorated.metadata.name
            if name in by_name:
                raise ValueError(f"Duplicate RPC handler: {name}")
            by_name[name] = decorated.function.__get__(owner)
    return by_name
