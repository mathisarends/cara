import asyncio
import logging
import uuid
from typing import Any
from uuid import UUID

from gateway.features.conversation.application.agent import (
    AgentChannelRef,
    AgentRunRequest,
    AgentRuntime,
    AgentSessionRef,
)
from gateway.features.conversation.application.events import (
    ConversationEvent,
    ConversationEventType,
)
from gateway.features.conversation.application.ports import EventPublisher, TurnLease
from gateway.features.conversation.application.session_service import SessionService
from gateway.features.conversation.application.turn_execution import TurnExecution
from gateway.features.conversation.domain import (
    NoActiveTurnError,
    Session,
    SessionBusyError,
    SessionRepository,
)
from gateway.shared import UnitOfWork

logger = logging.getLogger(__name__)

_AUTOMATION_BUSY_RETRY_SECONDS = 0.25
_MESSAGE_PREVIEW_LENGTH = 200


class TurnService:
    def __init__(
        self,
        sessions: UnitOfWork[SessionRepository],
        session_service: SessionService,
        leases: UnitOfWork[TurnLease],
        events: EventPublisher,
        agent: AgentRuntime,
    ) -> None:
        self._sessions = sessions
        self._session_service = session_service
        self._leases = leases
        self._events = events
        self._agent = agent
        self._background_tasks: dict[UUID, asyncio.Task[None]] = {}

    async def prepare(self, session_id: UUID) -> None:
        session = await self._session_service.get(session_id)
        session_ref = _agent_session_ref(session)
        await self._agent.prepare(session_ref)

    async def finish(self, session_id: UUID) -> None:
        session = await self._session_service.get(session_id)
        session_ref = _agent_session_ref(session)
        await self._agent.finish(session_ref)

    async def start(
        self,
        *,
        session_id: UUID,
        text: str,
    ) -> UUID:
        session = await self._session_service.get(session_id)
        if not await self._acquire_lease(session_id):
            raise SessionBusyError(session_id)
        # Acquiring the lease marks the session active in a separate unit of work.
        # Reload before saving the user message so stale aggregate state cannot
        # overwrite that flag.
        session = await self._session_service.get(session_id)
        logger.info(
            "User message for session %s on channel %s: %r",
            session_id,
            session.channel.name,
            _preview(text),
        )
        input_message = session.add_user_message(text)
        input_id = input_message.id
        await self._save(session)
        task = asyncio.create_task(
            self._execute(
                session_id,
                text,
                persist_input=False,
                input_id=input_id,
            )
        )
        self._background_tasks[session_id] = task
        task.add_done_callback(
            lambda completed, key=session_id: self._discard_task(key, completed)
        )
        await asyncio.sleep(0)
        return input_id

    async def start_scheduled(
        self,
        *,
        session_id: UUID,
        text: str,
    ) -> None:
        session = await self._session_service.get(session_id)
        deferred = False
        while not await self._acquire_lease(session_id):
            if not deferred:
                logger.info(
                    "Deferring automation for busy session %s until its turn ends",
                    session_id,
                )
                deferred = True
            await asyncio.sleep(_AUTOMATION_BUSY_RETRY_SECONDS)
        if deferred:
            logger.info("Resuming deferred automation for session %s", session_id)
        logger.info(
            "Scheduled prompt for session %s on channel %s: %r",
            session_id,
            session.channel.name,
            _preview(text),
        )
        await self._execute(session_id, text, persist_input=False)

    async def steer(self, *, session_id: UUID, text: str) -> None:
        session = await self._session_service.get(session_id)
        if not session.turn_active:
            raise NoActiveTurnError(session_id)
        logger.info(
            "User steered session %s on channel %s: %r",
            session_id,
            session.channel.name,
            _preview(text),
        )
        session_ref = _agent_session_ref(session)
        await self._agent.steer(session_ref, text)

    async def cancel(self, session_id: UUID) -> None:
        await self._session_service.get(session_id)
        task = self._background_tasks.get(session_id)
        if task is None or task.done():
            raise NoActiveTurnError(session_id)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        tasks = tuple(self._background_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute(
        self,
        session_id: UUID,
        text: str,
        *,
        persist_input: bool,
        input_id: UUID | None = None,
    ) -> None:
        session: Session | None = None
        turn: TurnExecution | None = None
        terminal_type = ConversationEventType.TURN_COMPLETED
        terminal_data: dict[str, Any] = {}
        try:
            session = await self._session_service.get(session_id)
            if persist_input:
                input_message = session.add_user_message(text)
                input_id = input_message.id
                session = await self._save(session)
            turn = TurnExecution(session, self._sessions, self._events)
            await turn.publish(ConversationEventType.TURN_STARTED, {})
            request = AgentRunRequest(
                session=_agent_session_ref(session),
                turn_id=uuid.uuid4(),
                input_id=input_id,
                input=text,
            )
            async for event in self._agent.run(request):
                await turn.handle(event)
        except asyncio.CancelledError:
            current_session = turn.session if turn else session
            await self._fail_pending_tool_calls(current_session, "Turn cancelled")
            terminal_type = ConversationEventType.TURN_CANCELLED
        except Exception as error:
            logger.exception("Conversation turn failed for session %s", session_id)
            current_session = turn.session if turn else session
            error_message = _message(error)
            await self._fail_pending_tool_calls(current_session, error_message)
            terminal_type = ConversationEventType.TURN_FAILED
            terminal_data = {
                "code": type(error).__name__,
                "message": error_message,
            }
        # The lease is released first so that a client may start the next turn
        # as soon as it sees the terminal event.
        try:
            await self._release_lease(session_id)
        finally:
            await self._publish_terminal(
                session,
                turn,
                terminal_type,
                terminal_data,
            )

    def _discard_task(self, session_id: UUID, completed: asyncio.Task[None]) -> None:
        if self._background_tasks.get(session_id) is completed:
            self._background_tasks.pop(session_id, None)

    async def _publish_terminal(
        self,
        session: Session | None,
        turn: TurnExecution | None,
        event_type: ConversationEventType,
        data: dict[str, Any],
    ) -> None:
        if turn is not None:
            await turn.publish(event_type, data)
            return
        if session is None:
            return
        await self._events.publish(
            ConversationEvent(
                type=event_type,
                session_id=session.id,
                channel=session.channel,
                sequence=1,
                data=data,
            )
        )

    async def _fail_pending_tool_calls(
        self,
        session: Session | None,
        error: str,
    ) -> None:
        if session is None or not session.fail_pending_tool_calls(error):
            return
        await self._save(session)

    async def _save(self, session: Session) -> Session:
        async with self._sessions() as sessions:
            return await sessions.save(session)

    async def _acquire_lease(self, session_id: UUID) -> bool:
        async with self._leases() as lease:
            return await lease.acquire(session_id)

    async def _release_lease(self, session_id: UUID) -> None:
        async with self._leases() as lease:
            await lease.release(session_id)


def _message(error: Exception) -> str:
    return str(error) or type(error).__name__


def _preview(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= _MESSAGE_PREVIEW_LENGTH:
        return normalized
    return f"{normalized[: _MESSAGE_PREVIEW_LENGTH - 1]}…"


def _agent_session_ref(session: Session) -> AgentSessionRef:
    return AgentSessionRef(
        id=session.id,
        channel=AgentChannelRef(session.channel.name),
        inactivity_timeout=session.inactivity_timeout,
    )
