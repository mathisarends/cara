import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from gateway_client import GatewayClient, connect_gateway
from gateway_client.models import (
    ChatCompleted,
    ChatDelta,
    SessionChannel,
    SessionEvent,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCancelled,
    TurnFailed,
    TurnStarted,
)
from gateway_client.models import (
    TurnCompleted as GatewayTurnCompleted,
)
from voice.activation import Activation, ActivationSource, PromptActivation
from voice.llm.events import (
    AgentEvent,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
)

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


class GatewayAgentSession(ActivationSource):
    def __init__(self, client: GatewayClient, session_id: UUID) -> None:
        self._client = client
        self._session_id = session_id
        self._turn_queue: asyncio.Queue[_QueuedEvent] | None = None
        self._turn_terminal: asyncio.Future[_QueuedEvent] | None = None
        self._activations: asyncio.Queue[Activation | None] = asyncio.Queue()
        self._proactive_turn_pending = False
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
        token: str,
        channel: str = "voice",
        new_session: bool = False,
    ) -> Self:
        client = await connect_gateway(url, token=token)
        try:
            return await cls.attach(
                client,
                channel=channel,
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
        new_session: bool = False,
    ) -> Self:
        channel_ref = SessionChannel(name=channel)
        if new_session:
            session = await client.session.create(channel=channel_ref)
        else:
            session = await client.session.open(channel=channel_ref)
        await client.subscription.subscribe(session_id=session.id)
        return cls(client, session.id)

    @property
    def session_id(self) -> UUID:
        return self._session_id

    async def prepare_turn(self) -> None:
        await self._client.turn.prepare(session_id=self._session_id)

    async def activations(self) -> AsyncIterator[Activation]:
        while (activation := await self._activations.get()) is not None:
            yield activation

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
        await self._client.turn.finish(session_id=self._session_id)

    async def steer(self, text: str) -> None:
        await self._client.turn.steer(session_id=self._session_id, message=text)

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
            await self._client.subscription.unsubscribe(session_id=self._session_id)
        finally:
            await self._client.close()
            await self._notifications
            await self._activations.put(None)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _begin_turn(self, text: str) -> asyncio.Queue[_QueuedEvent]:
        if self._closed:
            raise RuntimeError("Gateway agent session is closed")
        if self._proactive_turn_pending:
            self._proactive_turn_pending = False
            if self._turn_queue is None:
                raise RuntimeError("Proactive gateway turn has no event queue")
            return self._turn_queue
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
            async for event in self._client.session.event():
                if event.session_id != self._session_id:
                    continue
                if isinstance(event, TurnStarted) and self._turn_queue is None:
                    self._turn_queue = asyncio.Queue()
                    self._turn_terminal = asyncio.get_running_loop().create_future()
                    self._proactive_turn_pending = True
                    await self._activations.put(
                        PromptActivation(prompt="[Proactive gateway turn]")
                    )
                if self._turn_queue is None:
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
        await self._activations.put(None)

    def _finish_turn(self) -> None:
        self._proactive_turn_pending = False
        self._turn_queue = None
        terminal, self._turn_terminal = self._turn_terminal, None
        if terminal is not None and not terminal.done():
            terminal.cancel()
