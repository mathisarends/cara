import asyncio
import logging
from typing import Any
from uuid import UUID

from gateway.features.conversation.application.agent_event_router import (
    AgentEventRouter,
)
from gateway.features.conversation.application.event_bus import AgentEventBus
from gateway.features.conversation.application.ports import AgentRunner, EventPublisher
from gateway.features.conversation.domain import (
    GatewayEvent,
    GatewayEventType,
    Session,
    SessionBusyError,
    SessionNotFoundError,
    SessionRepository,
)

logger = logging.getLogger(__name__)


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
        self._background_tasks: dict[UUID, asyncio.Task[None]] = {}

    async def create_session(self, metadata: dict[str, Any]) -> Session:
        session = Session.create(metadata)
        return await self._sessions.save(session)

    async def get_session(self, session_id: UUID) -> Session:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    async def start_turn(
        self,
        session_id: UUID,
        text: str,
        metadata: dict[str, object],
    ) -> None:
        await self.get_session(session_id)
        if not await self._sessions.claim_turn(session_id):
            raise SessionBusyError(session_id)
        task = asyncio.create_task(self._execute(session_id, text, metadata))
        self._background_tasks[session_id] = task
        task.add_done_callback(
            lambda completed, key=session_id: self._discard_task(key, completed)
        )
        # Let the task enter its try/finally before callers can cancel it. This
        # guarantees that the claimed turn is released during shutdown too.
        await asyncio.sleep(0)

    async def cancel_turn(self, session_id: UUID) -> None:
        await self.get_session(session_id)
        task = self._background_tasks.get(session_id)
        if task is None or task.done():
            raise ValueError(f"Session {session_id} has no active turn")
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        tasks = tuple(self._background_tasks.items())
        for _, task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)

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
                1,
            )
            event_router.bind(event_bus)
            await self._events.publish(
                GatewayEvent(
                    type=GatewayEventType.TURN_STARTED,
                    session_id=session_id,
                    sequence=1,
                    data={},
                )
            )
            await self._agent.run(session.id, metadata, event_bus)
            await self._events.publish(
                GatewayEvent(
                    type=GatewayEventType.TURN_COMPLETED,
                    session_id=session_id,
                    sequence=event_router.sequence + 1,
                    data={},
                )
            )
        except asyncio.CancelledError:
            current_session = event_router.session if event_router else session
            await self._fail_pending_tool_calls(current_session, "Turn cancelled")
            await self._events.publish(
                GatewayEvent(
                    type=GatewayEventType.TURN_CANCELLED,
                    session_id=session_id,
                    sequence=event_router.sequence + 1 if event_router else 1,
                    data={},
                )
            )
        except Exception as error:
            logger.exception(
                "Conversation turn failed for session %s",
                session_id,
            )
            current_session = event_router.session if event_router else session
            await self._fail_pending_tool_calls(current_session, _message(error))
            await self._publish_turn_failed(session_id, event_router, error)
        finally:
            await self._sessions.release_turn(session_id)

    def _discard_task(self, session_id: UUID, completed: asyncio.Task[None]) -> None:
        if self._background_tasks.get(session_id) is completed:
            self._background_tasks.pop(session_id, None)

    async def _publish_turn_failed(
        self,
        session_id: UUID,
        event_router: AgentEventRouter | None,
        error: Exception,
    ) -> None:
        await self._events.publish(
            GatewayEvent(
                type=GatewayEventType.TURN_FAILED,
                session_id=session_id,
                sequence=event_router.sequence + 1 if event_router else 1,
                data={"code": type(error).__name__, "message": _message(error)},
            )
        )

    async def _fail_pending_tool_calls(
        self,
        session: Session | None,
        error: str,
    ) -> None:
        if session is None or not session.fail_pending_tool_calls(error):
            return
        await self._sessions.save(session)


def _message(error: Exception) -> str:
    return str(error) or type(error).__name__
