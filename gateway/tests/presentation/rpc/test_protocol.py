from dataclasses import replace

import pytest

from gateway.features.conversation.presentation.events import ChatDelta
from gateway.features.conversation.presentation.protocol import CONVERSATION_PROTOCOL
from gateway.features.conversation.presentation.rpc import CreateSessionParams
from gateway.features.conversation.presentation.schemas import SessionResponse
from gateway.presentation import rpc
from gateway.presentation.rpc.protocol import GatewayProtocol, rpc_feature


def test_protocol_derives_methods_from_decorated_handler_annotations() -> None:
    protocol = GatewayProtocol((CONVERSATION_PROTOCOL,))

    method = protocol.method("session.create")

    assert method.handler_name == "create_session"
    assert method.request_name == "CreateSessionRequest"
    assert method.params is CreateSessionParams
    assert method.result is SessionResponse


def test_protocol_derives_events_from_decorated_message_union() -> None:
    protocol = GatewayProtocol((CONVERSATION_PROTOCOL,))

    event = next(event for event in protocol.events if event.name == "chat.delta")

    assert event.payload is ChatDelta


def test_protocol_rejects_duplicate_method_names() -> None:
    method = CONVERSATION_PROTOCOL.methods[0]
    duplicate = replace(
        CONVERSATION_PROTOCOL,
        name="duplicate",
        methods=(method,),
        notifications=(),
        events=(),
    )

    with pytest.raises(ValueError, match="Duplicate RPC method: session.create"):
        GatewayProtocol((CONVERSATION_PROTOCOL, duplicate))


def test_feature_rejects_handler_without_typed_params() -> None:
    class InvalidRpcMethods(rpc.RpcHandler):
        @rpc.method("invalid", summary="Invalid handler for testing.")
        async def invalid(self, params) -> SessionResponse:
            raise AssertionError

    with pytest.raises(TypeError, match="params must be a Pydantic model"):
        rpc_feature("invalid", handlers=(InvalidRpcMethods,))
