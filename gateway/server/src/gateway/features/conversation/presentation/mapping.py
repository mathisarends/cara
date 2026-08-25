from gateway.features.conversation.domain import (
    AssistantMessage,
    ChannelRef,
    GatewayEvent,
    Session,
    ToolCallSequence,
    UserMessage,
)
from gateway.features.conversation.presentation.events import (
    SESSION_EVENT_ADAPTER,
    SessionEvent,
)
from gateway.features.conversation.presentation.schemas import (
    AssistantMessageItem,
    Item,
    SessionChannel,
    SessionResponse,
    SessionSnapshotResponse,
    ToolCallItem,
    ToolCallStatus,
    UserMessageItem,
)


def session_snapshot(session: Session) -> SessionSnapshotResponse:
    items: list[Item] = []
    for entry in session.entries:
        if isinstance(entry, UserMessage):
            items.append(
                UserMessageItem(
                    id=entry.id, created_at=entry.created_at, content=entry.content
                )
            )
        elif isinstance(entry, AssistantMessage):
            items.append(
                AssistantMessageItem(
                    id=entry.id, created_at=entry.created_at, content=entry.content
                )
            )
        elif isinstance(entry, ToolCallSequence):
            items.extend(
                ToolCallItem(
                    id=call.id,
                    created_at=call.created_at,
                    call_id=call.call_id,
                    name=call.function_name,
                    arguments=call.function_arguments,
                    status=ToolCallStatus(call.state.value),
                    result=call.result,
                    error=call.error,
                )
                for call in entry.calls
            )
    return SessionSnapshotResponse(
        session=session_response(session),
        items=tuple(items),
        turn_active=session.turn_active,
    )


def session_response(session: Session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        created_at=session.created_at,
        channel=_session_channel(session.channel),
        metadata=session.metadata,
    )


def _session_channel(channel: ChannelRef) -> SessionChannel:
    return SessionChannel(
        name=channel.name,
        account_id=channel.account_id,
    )


def session_event(event: GatewayEvent) -> SessionEvent:
    message = {
        "type": event.type,
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "session_id": event.session_id,
        "sequence": event.sequence,
        "metadata": event.metadata,
        **event.data,
    }
    if event.call_id is not None:
        message["call_id"] = event.call_id
    return SESSION_EVENT_ADAPTER.validate_python(message)
