import asyncio
import json
from typing import Any
from uuid import UUID

from gateway.features.conversation.application.ports import AgentRunner, EventPublisher
from gateway.features.conversation.domain import (
    ChatCompleted,
    ChatDelta,
    GatewayEvent,
    NoActiveTurnError,
    Session,
    SessionBusyError,
    SessionNotFoundError,
    SessionRepository,
    ToolCallCompleted,
    ToolCallStarted,
)


class ConversationService:
    def __init__(
        self,
        sessions: SessionRepository,
        events: EventPublisher,
        agent: AgentRunner,
    ) -> None:
        self._sessions = sessions
        self._events = events
        self._agent = agent
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    async def create_session(self, metadata: dict[str, Any]) -> Session:
        session = Session.create(metadata)
        return await self._sessions.save(session)

    async def get_session(self, session_id: UUID) -> Session:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def start_turn(
        self,
        session_id: UUID,
        text: str,
        metadata: dict[str, object],
    ) -> None:
        current = self._tasks.get(session_id)
        if current is not None and not current.done():
            raise SessionBusyError(session_id)
        task = asyncio.create_task(self._execute(session_id, text, metadata))
        self._tasks[session_id] = task
        task.add_done_callback(
            lambda completed: self._remove_task(session_id, completed)
        )

    async def cancel_turn(self, session_id: UUID) -> None:
        task = self._tasks.get(session_id)
        if task is None or task.done():
            raise NoActiveTurnError(session_id)
        task.cancel()

    async def close(self) -> None:
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _remove_task(
        self,
        session_id: UUID,
        completed: asyncio.Task[None],
    ) -> None:
        if self._tasks.get(session_id) is completed:
            self._tasks.pop(session_id)

    async def _execute(
        self,
        session_id: UUID,
        text: str,
        metadata: dict[str, object],
    ) -> None:
        sequence = 0
        session: Session | None = None
        try:
            sequence = await self._emit(
                session_id,
                "turn.started",
                {},
                sequence=sequence,
            )
            session = await self.get_session(session_id)
            session.add_user_message(text)
            session = await self._sessions.save(session)
            async for output in self._agent.stream(session.id, metadata):
                sequence = await self._emit_agent_output(
                    session,
                    output,
                    sequence,
                )
            await self._emit(
                session_id,
                "turn.completed",
                {},
                sequence=sequence,
            )
        except asyncio.CancelledError:
            await self._fail_pending_tool_calls(session, "Turn cancelled")
            await self._emit(
                session_id,
                "turn.cancelled",
                {},
                sequence=sequence,
            )
        except Exception as error:
            await self._fail_pending_tool_calls(session, str(error))
            await self._emit(
                session_id,
                "turn.failed",
                {"code": "agent_error", "message": str(error)},
                sequence=sequence,
            )

    async def _emit_agent_output(
        self,
        session: Session,
        output: ChatDelta | ChatCompleted | ToolCallStarted | ToolCallCompleted,
        sequence: int,
    ) -> int:
        if isinstance(output, ChatDelta):
            return await self._emit(
                session.id,
                "chat.delta",
                {"text": output.text},
                sequence=sequence,
                metadata=output.metadata,
            )
        if isinstance(output, ChatCompleted):
            session.add_assistant_message(output.text)
            await self._sessions.save(session)
            return await self._emit(
                session.id,
                "chat.completed",
                {"text": output.text, "finish_reason": output.finish_reason},
                sequence=sequence,
                metadata=output.metadata,
            )
        if isinstance(output, ToolCallStarted):
            session.add_tool_call(output.call_id, output.name, output.arguments)
            await self._sessions.save(session)
            return await self._emit(
                session.id,
                "tool_call.started",
                {"name": output.name, "arguments": output.arguments},
                sequence=sequence,
                call_id=output.call_id,
                metadata=output.metadata,
            )
        if output.is_error:
            session.fail_tool_call(output.call_id, _render_tool_value(output.result))
        else:
            session.resolve_tool_call(output.call_id, output.result)
        await self._sessions.save(session)
        return await self._emit(
            session.id,
            "tool_call.completed",
            {
                "name": output.name,
                "result": output.result,
                "is_error": output.is_error,
            },
            sequence=sequence,
            call_id=output.call_id,
            metadata=output.metadata,
        )

    async def _emit(
        self,
        session_id: UUID,
        event_type: str,
        data: dict[str, Any],
        *,
        sequence: int,
        call_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        next_sequence = sequence + 1
        await self._events.publish(
            GatewayEvent(
                type=event_type,
                session_id=session_id,
                call_id=call_id,
                sequence=next_sequence,
                metadata=metadata or {},
                data=data,
            )
        )
        return next_sequence

    async def _fail_pending_tool_calls(
        self,
        session: Session | None,
        error: str,
    ) -> None:
        if session is None or not session.fail_pending_tool_calls(error):
            return
        await self._sessions.save(session)


def _render_tool_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
