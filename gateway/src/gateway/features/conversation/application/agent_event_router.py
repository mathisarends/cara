import json
from typing import Any

from gateway.features.conversation.application.event_bus import AgentEventBus
from gateway.features.conversation.application.ports import EventPublisher
from gateway.features.conversation.domain import (
    ChatCompleted,
    ChatDelta,
    GatewayEvent,
    GatewayEventType,
    Session,
    SessionRepository,
    ToolCallCompleted,
    ToolCallStarted,
)


class AgentEventRouter:
    def __init__(
        self,
        session: Session,
        sessions: SessionRepository,
        publisher: EventPublisher,
        sequence: int,
    ) -> None:
        self._session = session
        self._sessions = sessions
        self._publisher = publisher
        self._sequence = sequence

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def session(self) -> Session:
        return self._session

    def bind(self, event_bus: AgentEventBus) -> None:
        event_bus.on(ChatDelta, self._chat_delta)
        event_bus.on(ChatCompleted, self._chat_completed)
        event_bus.on(ToolCallStarted, self._tool_call_started)
        event_bus.on(ToolCallCompleted, self._tool_call_completed)

    async def _chat_delta(self, event: ChatDelta) -> None:
        await self._publish(
            GatewayEventType.CHAT_DELTA,
            {"text": event.text},
            event.metadata,
        )

    async def _chat_completed(self, event: ChatCompleted) -> None:
        self._session.add_assistant_message(event.text)
        self._session = await self._sessions.save(self._session)
        await self._publish(
            GatewayEventType.CHAT_COMPLETED,
            {"text": event.text, "finish_reason": event.finish_reason},
            event.metadata,
        )

    async def _tool_call_started(self, event: ToolCallStarted) -> None:
        self._session.add_tool_call(event.call_id, event.name, event.arguments)
        self._session = await self._sessions.save(self._session)
        await self._publish(
            GatewayEventType.TOOL_CALL_STARTED,
            {"name": event.name, "arguments": event.arguments},
            event.metadata,
            call_id=event.call_id,
        )

    async def _tool_call_completed(self, event: ToolCallCompleted) -> None:
        if event.is_error:
            self._session.fail_tool_call(
                event.call_id,
                _render_tool_value(event.result),
            )
        else:
            self._session.resolve_tool_call(event.call_id, event.result)
        self._session = await self._sessions.save(self._session)
        await self._publish(
            GatewayEventType.TOOL_CALL_COMPLETED,
            {
                "name": event.name,
                "result": event.result,
                "is_error": event.is_error,
            },
            event.metadata,
            call_id=event.call_id,
        )

    async def _publish(
        self,
        event_type: GatewayEventType,
        data: dict[str, Any],
        metadata: dict[str, Any],
        *,
        call_id: str | None = None,
    ) -> None:
        self._sequence += 1
        await self._publisher.publish(
            GatewayEvent(
                type=event_type,
                session_id=self._session.id,
                call_id=call_id,
                sequence=self._sequence,
                metadata=metadata,
                data=data,
            )
        )


def _render_tool_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
