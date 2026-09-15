import json
from typing import Any

from gateway.features.conversation.application.agent import (
    AgentEvent,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnSteered,
)
from gateway.features.conversation.application.events import (
    ConversationEvent,
    ConversationEventType,
)
from gateway.features.conversation.application.ports import EventPublisher
from gateway.features.conversation.domain import Session, SessionRepository
from gateway.shared import UnitOfWork


class TurnExecution:
    def __init__(
        self,
        session: Session,
        sessions: UnitOfWork[SessionRepository],
        publisher: EventPublisher,
    ) -> None:
        self._session = session
        self._sessions = sessions
        self._publisher = publisher
        self._sequence = 0

    @property
    def session(self) -> Session:
        return self._session

    async def handle(self, event: AgentEvent) -> None:
        match event:
            case ChatDelta():
                await self.publish(
                    ConversationEventType.CHAT_DELTA,
                    {"text": event.text},
                    event.metadata,
                )
            case ChatCompleted():
                if event.text:
                    self._session.add_assistant_message(event.text)
                    await self._save_session()
                await self.publish(
                    ConversationEventType.CHAT_COMPLETED,
                    {"text": event.text, "finish_reason": event.finish_reason},
                    event.metadata,
                )
            case TurnSteered():
                self._session.add_user_message(event.text)
                await self._save_session()
                await self.publish(
                    ConversationEventType.TURN_STEERED,
                    {"text": event.text},
                    event.metadata,
                )
            case ToolCallStarted():
                self._session.add_tool_call(
                    event.call_id,
                    event.name,
                    event.arguments,
                )
                await self._save_session()
                await self.publish(
                    ConversationEventType.TOOL_CALL_STARTED,
                    {"name": event.name, "arguments": event.arguments},
                    event.metadata,
                    call_id=event.call_id,
                )
            case ToolCallCompleted():
                if event.is_error:
                    self._session.fail_tool_call(
                        event.call_id,
                        render_tool_value(event.result),
                    )
                else:
                    self._session.resolve_tool_call(event.call_id, event.result)
                await self._save_session()
                await self.publish(
                    ConversationEventType.TOOL_CALL_COMPLETED,
                    {
                        "name": event.name,
                        "result": event.result,
                        "is_error": event.is_error,
                    },
                    event.metadata,
                    call_id=event.call_id,
                )

    async def publish(
        self,
        event_type: ConversationEventType,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        *,
        call_id: str | None = None,
    ) -> None:
        self._sequence += 1
        await self._publisher.publish(
            ConversationEvent(
                type=event_type,
                session_id=self._session.id,
                channel=self._session.channel,
                call_id=call_id,
                sequence=self._sequence,
                metadata=metadata or {},
                data=data,
            )
        )

    async def save_session(self) -> None:
        await self._save_session()

    async def _save_session(self) -> None:
        async with self._sessions() as sessions:
            self._session = await sessions.save(self._session)


def render_tool_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
