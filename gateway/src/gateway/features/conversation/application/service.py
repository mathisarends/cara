import asyncio
from typing import Any
from uuid import UUID

from gateway.features.conversation.application.agent_event_router import (
    AgentEventRouter,
)
from gateway.features.conversation.application.event_bus import AgentEventBus
from gateway.features.conversation.application.ports import AgentRunner, EventPublisher
from gateway.features.conversation.domain import (
    NoActiveTurnError,
    Session,
    SessionBusyError,
    SessionNotFoundError,
    SessionRepository,
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
        session: Session | None = None
        event_router: AgentEventRouter | None = None
        try:
            session = await self.get_session(session_id)
            session.add_user_message(text)
            session = await self._sessions.save(session)
            event_bus = AgentEventBus()
            event_router = AgentEventRouter(
                session,
                self._sessions,
                self._events,
                0,
            )
            event_router.bind(event_bus)
            await self._agent.run(session.id, metadata, event_bus)
        except asyncio.CancelledError:
            current_session = event_router.session if event_router else session
            await self._fail_pending_tool_calls(current_session, "Turn cancelled")
        except Exception as error:
            current_session = event_router.session if event_router else session
            await self._fail_pending_tool_calls(current_session, str(error))

    async def _fail_pending_tool_calls(
        self,
        session: Session | None,
        error: str,
    ) -> None:
        if session is None or not session.fail_pending_tool_calls(error):
            return
        await self._sessions.save(session)
