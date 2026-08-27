import asyncio
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from agent_plugin_api import (
    AgentChannelRef,
    AgentEvent,
    AgentRunner,
    AgentRunRequest,
    AgentSessionRef,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
)
from gateway.features.conversation.application.ports import EventPublisher
from gateway.features.conversation.domain import (
    ChannelRef,
    GatewayEvent,
    GatewayEventType,
    Session,
    SessionBusyError,
    SessionNotFoundError,
    SessionRepository,
)

logger = logging.getLogger(__name__)

_AUTOMATION_BUSY_RETRY_SECONDS = 0.25


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
        self._session_open_lock = asyncio.Lock()

    async def create_session(
        self,
        channel: ChannelRef,
        metadata: dict[str, Any],
    ) -> Session:
        session = Session.create(channel, metadata)
        return await self._sessions.save(session)

    async def open_session(
        self,
        channel: ChannelRef,
        metadata: dict[str, Any],
    ) -> Session:
        async with self._session_open_lock:
            session = await self._sessions.find_latest_by_channel(channel)
            if session is not None:
                return session
            return await self.create_session(channel, metadata)

    async def get_session(self, session_id: UUID) -> Session:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    async def prepare_turn(self, session_id: UUID) -> None:
        session = await self.get_session(session_id)
        await self._agent.prepare(_agent_session_ref(session))

    async def finish_turn(self, session_id: UUID) -> None:
        session = await self.get_session(session_id)
        await self._agent.finish(_agent_session_ref(session))

    async def start_turn(
        self,
        session_id: UUID,
        text: str,
        metadata: dict[str, object],
    ) -> None:
        await self.get_session(session_id)
        if not await self._sessions.claim_turn(session_id):
            raise SessionBusyError(session_id)
        task = asyncio.create_task(
            self._execute(session_id, text, metadata, persist_input=True)
        )
        self._background_tasks[session_id] = task
        task.add_done_callback(
            lambda completed, key=session_id: self._discard_task(key, completed)
        )
        # Let the task enter its try/finally before callers can cancel it. This
        # guarantees that the claimed turn is released during shutdown too.
        await asyncio.sleep(0)

    async def run_automation_turn(
        self,
        session_id: UUID,
        text: str,
        metadata: dict[str, object],
    ) -> None:
        """Run a server-initiated turn without adding a synthetic user message."""
        await self.get_session(session_id)
        deferred = False
        while not await self._sessions.claim_turn(session_id):
            if not deferred:
                logger.info(
                    "Deferring automation for busy session %s until its turn ends",
                    session_id,
                )
                deferred = True
            await asyncio.sleep(_AUTOMATION_BUSY_RETRY_SECONDS)
        if deferred:
            logger.info("Resuming deferred automation for session %s", session_id)
        await self._execute(session_id, text, metadata, persist_input=False)

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
        *,
        persist_input: bool,
    ) -> None:
        session: Session | None = None
        turn: _TurnExecution | None = None
        try:
            session = await self.get_session(session_id)
            input_id: UUID | None = None
            if persist_input:
                input_message = session.add_user_message(text)
                input_id = input_message.id
                session = await self._sessions.save(session)
            turn = _TurnExecution(
                session,
                self._sessions,
                self._events,
            )
            await turn.publish(GatewayEventType.TURN_STARTED, {})
            request = AgentRunRequest(
                session=_agent_session_ref(session),
                turn_id=uuid4(),
                input_id=input_id,
                input=text,
                turn_metadata=dict(metadata),
            )
            async for event in self._agent.run(request):
                await turn.handle(event)
            await turn.publish(GatewayEventType.TURN_COMPLETED, {})
        except asyncio.CancelledError:
            current_session = turn.session if turn else session
            await self._fail_pending_tool_calls(current_session, "Turn cancelled")
            await self._publish_terminal(
                session_id,
                turn,
                GatewayEventType.TURN_CANCELLED,
                {},
            )
        except Exception as error:
            logger.exception(
                "Conversation turn failed for session %s",
                session_id,
            )
            current_session = turn.session if turn else session
            await self._fail_pending_tool_calls(current_session, _message(error))
            await self._publish_terminal(
                session_id,
                turn,
                GatewayEventType.TURN_FAILED,
                {"code": type(error).__name__, "message": _message(error)},
            )
        finally:
            await self._sessions.release_turn(session_id)

    def _discard_task(self, session_id: UUID, completed: asyncio.Task[None]) -> None:
        if self._background_tasks.get(session_id) is completed:
            self._background_tasks.pop(session_id, None)

    async def _publish_terminal(
        self,
        session_id: UUID,
        turn: "_TurnExecution | None",
        event_type: GatewayEventType,
        data: dict[str, Any],
    ) -> None:
        if turn is not None:
            await turn.publish(event_type, data)
            return
        await self._events.publish(
            GatewayEvent(
                type=event_type,
                session_id=session_id,
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
        await self._sessions.save(session)


class _TurnExecution:
    def __init__(
        self,
        session: Session,
        sessions: SessionRepository,
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
                    GatewayEventType.CHAT_DELTA,
                    {"text": event.text},
                    event.metadata,
                )
            case ChatCompleted():
                if event.text:
                    self._session.add_assistant_message(event.text)
                    await self._save_session()
                await self.publish(
                    GatewayEventType.CHAT_COMPLETED,
                    {"text": event.text, "finish_reason": event.finish_reason},
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
                    GatewayEventType.TOOL_CALL_STARTED,
                    {"name": event.name, "arguments": event.arguments},
                    event.metadata,
                    call_id=event.call_id,
                )
            case ToolCallCompleted():
                if event.is_error:
                    self._session.fail_tool_call(
                        event.call_id,
                        _render_tool_value(event.result),
                    )
                else:
                    self._session.resolve_tool_call(event.call_id, event.result)
                await self._save_session()
                await self.publish(
                    GatewayEventType.TOOL_CALL_COMPLETED,
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
        event_type: GatewayEventType,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
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
                metadata=metadata or {},
                data=data,
            )
        )

    async def _save_session(self) -> None:
        self._session = await self._sessions.save(self._session)


def _message(error: Exception) -> str:
    return str(error) or type(error).__name__


def _agent_session_ref(session: Session) -> AgentSessionRef:
    return AgentSessionRef(
        id=session.id,
        channel=AgentChannelRef(
            name=session.channel.name,
            account_id=session.channel.account_id,
        ),
    )


def _render_tool_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
