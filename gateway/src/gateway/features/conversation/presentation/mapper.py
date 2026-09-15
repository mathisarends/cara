from collections.abc import Iterable

from gateway.features.conversation import domain
from gateway.features.conversation.presentation.schemas import (
    AssistantMessageItem,
    Item,
    ItemType,
    SessionChannel,
    SessionListResponse,
    SessionResponse,
    SessionSnapshotResponse,
    SortOrder,
    ToolCallItem,
    ToolCallStatus,
    UserMessageItem,
)


def to_channel_ref(channel: SessionChannel) -> domain.ChannelRef:
    return domain.ChannelRef(channel.name)


def to_sort_order(sort: SortOrder) -> domain.SortOrder:
    match sort:
        case SortOrder.ASC:
            return domain.SortOrder.ASCENDING
        case SortOrder.DESC:
            return domain.SortOrder.DESCENDING


def to_session_list_response(
    sessions: Iterable[domain.Session],
) -> SessionListResponse:
    return SessionListResponse(
        sessions=tuple(to_session_response(session) for session in sessions)
    )


def to_session_response(session: domain.Session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        created_at=session.created_at,
        channel=SessionChannel(name=session.channel.name),
    )


def to_session_snapshot_response(session: domain.Session) -> SessionSnapshotResponse:
    return SessionSnapshotResponse(
        session=to_session_response(session),
        items=tuple(item for entry in session.entries for item in _to_items(entry)),
        turn_active=session.turn_active,
    )


def _to_items(entry: domain.SessionEntry) -> tuple[Item, ...]:
    match entry:
        case domain.UserMessage():
            return (
                UserMessageItem(
                    type=ItemType.USER_MESSAGE,
                    id=entry.id,
                    created_at=entry.created_at,
                    content=entry.content,
                ),
            )
        case domain.AssistantMessage():
            return (
                AssistantMessageItem(
                    type=ItemType.ASSISTANT_MESSAGE,
                    id=entry.id,
                    created_at=entry.created_at,
                    content=entry.content,
                ),
            )
        case domain.ToolCallSequence():
            return tuple(_to_tool_call_item(call) for call in entry.calls)


def _to_tool_call_item(call: domain.ToolCall) -> ToolCallItem:
    return ToolCallItem(
        type=ItemType.TOOL_CALL,
        id=call.id,
        created_at=call.created_at,
        call_id=call.call_id,
        name=call.function_name,
        arguments=call.function_arguments,
        status=ToolCallStatus(call.state.value),
        result=call.result,
        error=call.error,
    )
