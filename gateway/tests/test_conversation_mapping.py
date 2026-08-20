from gateway.features.conversation.domain import (
    GatewayEvent,
    GatewayEventType,
    Session,
)
from gateway.features.conversation.presentation.mapping import (
    session_event,
    session_snapshot,
)


def test_session_snapshot_maps_persisted_entries() -> None:
    session = Session.create({"channel": "test"})
    session.add_user_message("hello")
    session.add_assistant_message("hi")

    snapshot = session_snapshot(session)

    assert snapshot.session.id == session.id
    assert [item.type for item in snapshot.items] == [
        "user_message",
        "assistant_message",
    ]


def test_gateway_event_maps_to_flat_protocol_event() -> None:
    session = Session.create()
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
