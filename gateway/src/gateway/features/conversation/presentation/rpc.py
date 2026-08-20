from enum import StrEnum
from uuid import UUID

from pydantic import Field

from gateway.features.conversation.presentation.schemas import WireSchema


class RpcNotificationMethod(StrEnum):
    SESSION_EVENT = "session.event"


class SessionParams(WireSchema):
    session_id: UUID


class CreateSessionParams(WireSchema):
    metadata: dict[str, object] = Field(default_factory=dict)


class StartTurnParams(SessionParams):
    message: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class SubscriptionResult(WireSchema):
    subscribed: UUID


class UnsubscriptionResult(WireSchema):
    unsubscribed: UUID


class TurnCommandResult(WireSchema):
    session_id: UUID
