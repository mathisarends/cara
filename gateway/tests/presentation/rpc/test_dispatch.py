import pytest
from pydantic import BaseModel

from gateway.presentation import rpc
from gateway.presentation.rpc.dispatch import GatewayRpcMethods, RpcInvalidParamsError
from gateway.presentation.rpc.protocol import GatewayProtocol, rpc_feature


class _EchoParams(BaseModel):
    text: str


class _EchoResult(BaseModel):
    text: str


class _EchoHandler(rpc.RpcHandler):
    def __init__(self) -> None:
        self.calls: list[_EchoParams] = []

    @rpc.method("echo", summary="Echo params back.")
    async def echo(self, params: _EchoParams) -> _EchoResult:
        self.calls.append(params)
        return _EchoResult(text=params.text)


_ECHO_FEATURE = rpc_feature("echo", handlers=(_EchoHandler,))


@pytest.fixture
def protocol() -> GatewayProtocol:
    return GatewayProtocol((_ECHO_FEATURE,))


@pytest.fixture
def handler() -> _EchoHandler:
    return _EchoHandler()


def test_parse_request_resolves_method_and_validates_params(
    protocol: GatewayProtocol,
    handler: _EchoHandler,
) -> None:
    methods = GatewayRpcMethods(protocol, (handler,))

    invocation = methods.parse_request(
        {"jsonrpc": "2.0", "id": 1, "method": "echo", "params": {"text": "hi"}}
    )

    assert invocation.method.handler_name == "echo"
    assert isinstance(invocation.params, _EchoParams)
    assert invocation.params.text == "hi"


async def test_execute_invokes_the_bound_handler(
    protocol: GatewayProtocol,
    handler: _EchoHandler,
) -> None:
    methods = GatewayRpcMethods(protocol, (handler,))
    invocation = methods.parse_request(
        {"jsonrpc": "2.0", "id": 1, "method": "echo", "params": {"text": "hi"}}
    )

    result = await methods.execute(invocation)

    assert result == _EchoResult(text="hi")
    assert handler.calls == [invocation.params]


def test_parse_request_rejects_invalid_params(
    protocol: GatewayProtocol,
    handler: _EchoHandler,
) -> None:
    methods = GatewayRpcMethods(protocol, (handler,))

    with pytest.raises(RpcInvalidParamsError, match="params.text"):
        methods.parse_request(
            {"jsonrpc": "2.0", "id": 1, "method": "echo", "params": {}}
        )


def test_construction_rejects_handlers_that_do_not_match_the_protocol(
    protocol: GatewayProtocol,
) -> None:
    class _OtherHandler(rpc.RpcHandler):
        @rpc.method("other", summary="Unrelated method.")
        async def other(self, params: _EchoParams) -> _EchoResult:
            raise AssertionError

    with pytest.raises(
        ValueError,
        match=r"missing=\['echo'\], unexpected=\['other'\]",
    ):
        GatewayRpcMethods(protocol, (_OtherHandler(),))


def test_construction_rejects_two_handlers_bound_to_the_same_method(
    protocol: GatewayProtocol,
    handler: _EchoHandler,
) -> None:
    with pytest.raises(ValueError, match="Duplicate RPC handler: echo"):
        GatewayRpcMethods(protocol, (handler, _EchoHandler()))
