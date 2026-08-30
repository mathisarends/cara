from gateway.features.conversation.domain import (
    ChannelRef,
    GatewayEvent,
    GatewayEventType,
    Session,
)
from gateway.features.conversation.presentation.rpc.mapping import (
    session_event,
    session_snapshot,
)

_CHANNEL = ChannelRef("test")


def test_session_snapshot_maps_persisted_entries() -> None:
    session = Session.create(_CHANNEL)
    session.add_user_message("hello")
    session.add_assistant_message("hi")

    snapshot = session_snapshot(session)

    assert snapshot.session.id == session.id
    assert snapshot.session.channel.name == "test"
    assert [item.type for item in snapshot.items] == [
        "user_message",
        "assistant_message",
    ]


def test_gateway_event_maps_to_flat_protocol_event() -> None:
    session = Session.create(_CHANNEL)
    event = GatewayEvent(
        type=GatewayEventType.CHAT_DELTA,
        session_id=session.id,
        sequence=2,
        data={"text": "Hi"},
    )

    message = session_event(event)

    assert message.type == "chat.delta"
    assert message.text == "Hi"
    assert "data" not in message.model_dump()
