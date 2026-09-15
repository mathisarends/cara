import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Self
from uuid import UUID

import httpx2

from gateway_rest_client import (
    CreateSessionRequest,
    GatewayRestClient,
    OpenSessionRequest,
    SessionChannel,
)
from gateway_rpc_client import GatewayRpcClient, connect_gateway
from gateway_rpc_client.models import (
    ChatCompleted,
    ChatDelta,
    SessionEvent,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCancelled,
    TurnFailed,
    TurnStarted,
)
from gateway_rpc_client.models import (
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
    def __init__(
        self,
        client: GatewayRpcClient,
        session_id: UUID,
        channel: str,
        *,
        sessions: GatewayRestClient | None = None,
        http: httpx2.AsyncClient | None = None,
        inactivity_timeout_seconds: float | None = None,
    ) -> None:
        self._client = client
        self._session_id = session_id
        self._channel = channel
        self._sessions = sessions
        self._http = http
        self._inactivity_timeout_seconds = inactivity_timeout_seconds
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
        inactivity_timeout_seconds: float = 1800,
    ) -> Self:
        http = httpx2.AsyncClient()
        sessions = GatewayRestClient(http, url, credentials={"GatewayToken": token})
        client: GatewayRpcClient | None = None
        try:
            session_id = await _resolve_session(
                sessions,
                channel=channel,
                new_session=new_session,
                inactivity_timeout_seconds=inactivity_timeout_seconds,
            )
            client = await connect_gateway(url, token=token)
            await client.subscription.subscribe_channel(channel=channel)
            return cls(
                client,
                session_id,
                channel,
                sessions=sessions,
                http=http,
                inactivity_timeout_seconds=inactivity_timeout_seconds,
            )
        except BaseException:
            if client is not None:
                await client.close()
            await http.aclose()
            raise

    @classmethod
    async def attach(
        cls,
        client: GatewayRpcClient,
        session_id: UUID,
        *,
        channel: str = "voice",
    ) -> Self:
        await client.subscription.subscribe_channel(channel=channel)
        return cls(client, session_id, channel)

    @property
    def session_id(self) -> UUID:
        return self._session_id

    async def prepare_turn(self) -> None:
        await self._refresh_session()
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
            await self._client.subscription.unsubscribe_channel(channel=self._channel)
        finally:
            await self._client.close()
            if self._http is not None:
                await self._http.aclose()
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
        await self._refresh_session()
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
                if isinstance(event, TurnStarted) and self._turn_queue is None:
                    self._session_id = event.session_id
                    self._turn_queue = asyncio.Queue()
                    self._turn_terminal = asyncio.get_running_loop().create_future()
                    self._proactive_turn_pending = True
                    await self._activations.put(
                        PromptActivation(prompt="[Proactive gateway turn]")
                    )
                if self._turn_queue is None:
                    continue
                if event.session_id != self._session_id:
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

    async def _refresh_session(self) -> None:
        if self._sessions is None:
            return
        self._session_id = await _resolve_session(
            self._sessions,
            channel=self._channel,
            new_session=False,
            inactivity_timeout_seconds=self._inactivity_timeout_seconds,
        )


async def _resolve_session(
    sessions: GatewayRestClient,
    *,
    channel: str,
    new_session: bool,
    inactivity_timeout_seconds: float | None,
) -> UUID:
    channel_ref = SessionChannel(name=channel)
    if new_session:
        request = CreateSessionRequest(
            channel=channel_ref,
            inactivity_timeout_seconds=inactivity_timeout_seconds,
        )
        session = await sessions.create_session(request)
    else:
        request = OpenSessionRequest(
            channel=channel_ref,
            inactivity_timeout_seconds=inactivity_timeout_seconds,
        )
        session = await sessions.open_session(request)
    return session.id
