from enum import StrEnum
from uuid import UUID

from pydantic import Field

from gateway.features.conversation.presentation.schemas import (
    SessionChannel,
    WireSchema,
)


class ConversationRpcMethod(StrEnum):
    SESSION_CREATE = "session.create"
    SESSION_OPEN = "session.open"
    SESSION_GET = "session.get"
    SESSION_SUBSCRIBE = "session.subscribe"
    SESSION_UNSUBSCRIBE = "session.unsubscribe"
    TURN_START = "turn.start"
    TURN_CANCEL = "turn.cancel"


class RpcNotificationMethod(StrEnum):
    SESSION_EVENT = "session.event"


class SessionParams(WireSchema):
    session_id: UUID


class CreateSessionParams(WireSchema):
    channel: SessionChannel
    metadata: dict[str, object] = Field(default_factory=dict)


class OpenSessionParams(CreateSessionParams):
    pass


class StartTurnParams(SessionParams):
    message: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class SubscriptionResult(WireSchema):
    subscribed: UUID


class UnsubscriptionResult(WireSchema):
    unsubscribed: UUID


class TurnCommandResult(WireSchema):
    session_id: UUID
