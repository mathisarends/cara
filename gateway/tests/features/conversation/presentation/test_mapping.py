from gateway.features.conversation.application import (
    ConversationEventType,
    create_conversation_event,
)
from gateway.features.conversation.domain import ChannelRef, Session
from gateway.features.conversation.presentation.mapper import (
    to_session_snapshot_response,
)
from gateway.features.conversation.presentation.rpc.mapping import session_event

_CHANNEL = ChannelRef("test")


def test_session_snapshot_maps_persisted_entries() -> None:
    session = Session.create(_CHANNEL)
    session.add_user_message("hello")
    session.add_assistant_message("hi")

    snapshot = to_session_snapshot_response(session)

    assert snapshot.session.id == session.id
    assert snapshot.session.channel.name == "test"
    assert [item.type for item in snapshot.items] == [
        "user_message",
        "assistant_message",
    ]


def test_conversation_event_maps_to_a_flat_protocol_event() -> None:
    session = Session.create(_CHANNEL)
    event = create_conversation_event(
        ConversationEventType.CHAT_DELTA,
        session.id,
        session.channel,
        {"text": "Hi"},
        sequence=2,
    )

    message = session_event(event)

    assert message.type == "chat.delta"
    assert message.text == "Hi"
    assert "data" not in message.model_dump()
