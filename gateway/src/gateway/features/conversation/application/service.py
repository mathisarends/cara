import asyncio
from datetime import UTC, datetime
from typing import Any

from gateway.features.conversation.application.ports import AgentRunner, EventPublisher
from gateway.features.conversation.domain import (
    ChatCompleted,
    ChatDelta,
    GatewayEvent,
    Run,
    RunNotFoundError,
    RunRepository,
    Session,
    SessionNotFoundError,
    SessionRepository,
    ToolCallCompleted,
    ToolCallStarted,
)
from gateway.features.conversation.domain.models import new_id


class ConversationService:
    def __init__(
        self,
        sessions: SessionRepository,
        runs: RunRepository,
        events: EventPublisher,
        agent: AgentRunner,
    ) -> None:
        self._sessions = sessions
        self._runs = runs
        self._events = events
        self._agent = agent
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def create_session(self, metadata: dict[str, Any]) -> Session:
        session = Session(
            id=new_id("sess"),
            created_at=datetime.now(UTC),
            metadata=dict(metadata),
        )
        return await self._sessions.save(session)

    async def get_session(self, session_id: str) -> Session:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    async def prepare_run(self, session_id: str) -> Run:
        await self.get_session(session_id)
        run = Run(
            id=new_id("run"),
            session_id=session_id,
            created_at=datetime.now(UTC),
        )
        return await self._runs.save(run)

    def start_run(
        self,
        run: Run,
        text: str,
        metadata: dict[str, object],
    ) -> None:
        task = asyncio.create_task(self._execute(run, text, metadata))
        self._tasks[run.id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run.id, None))

    async def cancel_run(self, session_id: str, run_id: str) -> Run:
        run = await self._runs.find_by_id(run_id)
        if run is None or run.session_id != session_id:
            raise RunNotFoundError(run_id)
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
        return run

    async def close(self) -> None:
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute(
        self,
        run: Run,
        text: str,
        metadata: dict[str, object],
    ) -> None:
        sequence = 0
        try:
            run.status = "running"
            run = await self._runs.save(run)
            sequence = await self._emit(run, "run.started", {}, sequence=sequence)
            session = await self.get_session(run.session_id)
            async for output in self._agent.stream(session, text, metadata):
                sequence = await self._emit_agent_output(run, output, sequence)
            run.status = "completed"
            run = await self._runs.save(run)
            await self._emit(
                run,
                "run.completed",
                {"status": run.status},
                sequence=sequence,
            )
        except asyncio.CancelledError:
            run.status = "cancelled"
            run = await self._runs.save(run)
            await self._emit(
                run,
                "run.cancelled",
                {"status": run.status},
                sequence=sequence,
            )
        except Exception as error:
            run.status = "failed"
            run = await self._runs.save(run)
            await self._emit(
                run,
                "run.failed",
                {"code": "agent_error", "message": str(error)},
                sequence=sequence,
            )

    async def _emit_agent_output(
        self,
        run: Run,
        output: ChatDelta | ChatCompleted | ToolCallStarted | ToolCallCompleted,
        sequence: int,
    ) -> int:
        if isinstance(output, ChatDelta):
            return await self._emit(
                run,
                "chat.delta",
                {"text": output.text},
                sequence=sequence,
                metadata=output.metadata,
            )
        if isinstance(output, ChatCompleted):
            return await self._emit(
                run,
                "chat.completed",
                {"text": output.text, "finish_reason": output.finish_reason},
                sequence=sequence,
                metadata=output.metadata,
            )
        if isinstance(output, ToolCallStarted):
            return await self._emit(
                run,
                "tool_call.started",
                {"name": output.name, "arguments": output.arguments},
                sequence=sequence,
                call_id=output.call_id,
                metadata=output.metadata,
            )
        return await self._emit(
            run,
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
        run: Run,
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
                session_id=run.session_id,
                run_id=run.id,
                call_id=call_id,
                sequence=next_sequence,
                metadata=metadata or {},
                data=data,
            )
        )
        return next_sequence
