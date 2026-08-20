import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from gateway_client import GatewayClient
from gateway_client.models import (
    ChatCompleted,
    ChatDelta,
    SessionChannel,
    SessionEvent,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCancelled,
    TurnFailed,
)
from gateway_client.models import (
    TurnCompleted as GatewayTurnCompleted,
)
from voice.llm.events import (
    AgentEvent,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
)

_SESSION_METADATA = {"client": "cara-voice"}
_TURN_METADATA = {"modality": "voice"}


class GatewayAgentTurnError(RuntimeError):
    pass


class GatewayAgentTurnCancelled(GatewayAgentTurnError):
    def __init__(self) -> None:
        super().__init__("Gateway agent turn was cancelled")


class GatewayAgentTurnFailed(GatewayAgentTurnError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class _GatewayDisconnected:
    error: Exception


type _QueuedEvent = SessionEvent | _GatewayDisconnected


class GatewayAgentSession:
    def __init__(self, client: GatewayClient, session_id: UUID) -> None:
        self._client = client
        self._session_id = session_id
        self._turn_queue: asyncio.Queue[_QueuedEvent] | None = None
        self._turn_terminal: asyncio.Future[_QueuedEvent] | None = None
        self._closed = False
        self._notifications = asyncio.create_task(
            self._pump_notifications(),
            name="voice-gateway-notifications",
        )

    @classmethod
    async def connect(
        cls,
        url: str,
        *,
        channel: str = "voice",
        account_id: str | None = None,
        new_session: bool = False,
    ) -> Self:
        client = await GatewayClient.connect(url)
        try:
            return await cls.attach(
                client,
                channel=channel,
                account_id=account_id,
                new_session=new_session,
            )
        except BaseException:
            await client.close()
            raise

    @classmethod
    async def attach(
        cls,
        client: GatewayClient,
        *,
        channel: str = "voice",
        account_id: str | None = None,
        new_session: bool = False,
    ) -> Self:
        channel_ref = SessionChannel(name=channel, account_id=account_id)
        if new_session:
            session = await client.session.create(
                channel=channel_ref,
                metadata=_SESSION_METADATA,
            )
        else:
            session = await client.session.open(
                channel=channel_ref,
                metadata=_SESSION_METADATA,
            )
        await client.session.subscribe(session_id=session.id)
        return cls(client, session.id)

    @property
    def session_id(self) -> UUID:
        return self._session_id

    async def prepare_turn(self) -> None:
        pass

    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        return self._stream_turn(text)

    async def _stream_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        queue = await self._begin_turn(text)
        streamed_text = False
        completed_text = ""
        finish_reason = "stop"
        while True:
            event = await queue.get()
            if isinstance(event, _GatewayDisconnected):
                self._finish_turn()
                raise event.error
            match event:
                case ChatDelta():
                    streamed_text = True
                    yield TextDelta(event.text)
                case ChatCompleted():
                    completed_text = event.text
                    finish_reason = event.finish_reason
                    if event.text and not streamed_text:
                        yield TextDelta(event.text)
                case ToolCallStarted():
                    yield ToolStarted(
                        event.name,
                        event.call_id,
                        event.arguments,
                    )
                case ToolCallCompleted():
                    yield ToolCompleted(
                        event.name,
                        event.call_id,
                        event.result,
                        event.is_error,
                    )
                case GatewayTurnCompleted():
                    self._finish_turn()
                    yield TurnCompleted(completed_text, finish_reason)
                    return
                case TurnCancelled():
                    self._finish_turn()
                    raise GatewayAgentTurnCancelled()
                case TurnFailed():
                    self._finish_turn()
                    raise GatewayAgentTurnFailed(event.code, event.message)

    async def finish_turn(self) -> None:
        pass

    async def steer(self, text: str) -> None:
        del text
        raise NotImplementedError("Gateway agent sessions do not support steering")

    async def interrupt(self) -> None:
        terminal = self._turn_terminal
        if terminal is None:
            return
        await self._client.turn.cancel(session_id=self._session_id)
        event = await asyncio.shield(terminal)
        self._finish_turn()
        if isinstance(event, _GatewayDisconnected):
            raise event.error

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self.interrupt()
            await self._client.session.unsubscribe(session_id=self._session_id)
        finally:
            await self._client.close()
            await self._notifications

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _begin_turn(self, text: str) -> asyncio.Queue[_QueuedEvent]:
        if self._closed:
            raise RuntimeError("Gateway agent session is closed")
        if self._turn_terminal is not None:
            raise RuntimeError("Gateway agent session already has an active turn")
        queue: asyncio.Queue[_QueuedEvent] = asyncio.Queue()
        self._turn_queue = queue
        self._turn_terminal = asyncio.get_running_loop().create_future()
        try:
            await self._client.turn.start(
                session_id=self._session_id,
                message=text,
                metadata=_TURN_METADATA,
            )
        except BaseException:
            self._finish_turn()
            raise
        return queue

    async def _pump_notifications(self) -> None:
        try:
            async for notification in self._client.notifications():
                event = notification.params
                if event.session_id != self._session_id or self._turn_queue is None:
                    continue
                await self._turn_queue.put(event)
                if isinstance(event, GatewayTurnCompleted | TurnCancelled | TurnFailed):
                    terminal = self._turn_terminal
                    if terminal is not None and not terminal.done():
                        terminal.set_result(event)
        except Exception as error:
            await self._notify_disconnected(error)
        else:
            if not self._closed:
                await self._notify_disconnected(
                    GatewayAgentTurnError("Gateway connection closed")
                )

    async def _notify_disconnected(self, error: Exception) -> None:
        disconnected = _GatewayDisconnected(error)
        if self._turn_queue is not None:
            await self._turn_queue.put(disconnected)
        terminal = self._turn_terminal
        if terminal is not None and not terminal.done():
            terminal.set_result(disconnected)

    def _finish_turn(self) -> None:
        self._turn_queue = None
        terminal, self._turn_terminal = self._turn_terminal, None
        if terminal is not None and not terminal.done():
            terminal.cancel()
