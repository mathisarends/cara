import asyncio
from uuid import UUID

from pyrpckit.client import RpcRemoteError

from cli.console import Console
from cli.keyboard import Character, ControlKey, Keyboard
from gateway_client import GatewayClient
from gateway_client.models import (
    AssistantMessageItem,
    ChatCompleted,
    ChatDelta,
    Item,
    SessionChannel,
    SessionEvent,
    ToolCallCompleted,
    ToolCallItem,
    ToolCallStarted,
    ToolCallStatus,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
    TurnSteered,
    UserMessageItem,
)

_METADATA = {"client": "cara-cli"}

# gateway.presentation.rpc.GatewayErrorCode.NO_ACTIVE_TURN
_NO_ACTIVE_TURN = -32010

_IDLE_HINT = "type a message, /help for commands"
_BUSY_HINT = "type to steer · esc to interrupt"

_HELP = """\
enter             send, or queue a steering message while a turn runs
esc               clear the input, or interrupt the running turn
/new              start a fresh session on the channel
/session          show the current session id
/history          replay the session snapshot from the gateway
/events           toggle the raw event trace
/cancel           interrupt the running turn
/quit             leave (ctrl-c works too)\
"""


class ChatSession:
    def __init__(
        self,
        client: GatewayClient,
        console: Console,
        keyboard: Keyboard,
        channel: SessionChannel,
        trace: bool,
    ) -> None:
        self._client = client
        self._console = console
        self._keyboard = keyboard
        self._channel = channel
        self._trace = trace
        self._session_id: UUID | None = None
        self._turn_active = False
        self._queued: list[str] = []
        self._streaming = False

    async def run(self, session_id: UUID | None) -> None:
        pump = asyncio.create_task(self._pump_events())
        try:
            await self._open(session_id)
            await self._interact()
        finally:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
            self._console.close()

    async def _open(self, session_id: UUID | None) -> None:
        if session_id is None:
            session = await self._client.session.open(
                channel=self._channel,
                metadata=_METADATA,
            )
            session_id = session.id
        await self._attach(session_id)

    async def _create(self) -> None:
        session = await self._client.session.create(
            channel=self._channel,
            metadata=_METADATA,
        )
        await self._attach(session.id)

    async def _attach(self, session_id: UUID) -> None:
        if self._session_id is not None:
            await self._client.subscription.unsubscribe(session_id=self._session_id)
        snapshot = await self._client.session.get(session_id=session_id)
        self._session_id = session_id
        self._turn_active = snapshot.turn_active
        self._console.info(f"session {session_id} on channel {self._channel.name}")
        self._replay(snapshot.items)
        await self._client.subscription.subscribe(session_id=session_id)
        self._update_hint()

    async def _interact(self) -> None:
        async for key in self._keyboard.events():
            match key:
                case Character(value=value):
                    self._console.type(value)
                case ControlKey.BACKSPACE:
                    self._console.backspace()
                case ControlKey.SUBMIT:
                    if not await self._submit(self._console.take_input().strip()):
                        return
                case ControlKey.ESCAPE:
                    await self._escape()
                case ControlKey.QUIT:
                    return
                case ControlKey.UNKNOWN:
                    pass

    async def _submit(self, line: str) -> bool:
        if not line:
            return True
        if line.startswith("/"):
            return await self._run_command(line)
        self._console.user(line)
        await self._say(line)
        return True

    async def _escape(self) -> None:
        if self._console.input:
            self._console.take_input()
            return
        await self._cancel_turn()

    async def _cancel_turn(self) -> None:
        if not self._turn_active:
            return
        try:
            await self._client.turn.cancel(session_id=self._session_id)
        except RpcRemoteError as error:
            if error.code != _NO_ACTIVE_TURN:
                raise
            self._turn_finished()

    async def _run_command(self, line: str) -> bool:
        match line.split():
            case ["/quit" | "/exit" | "/q"]:
                return False
            case ["/help" | "/h"]:
                self._console.info(_HELP)
            case ["/new"]:
                await self._create()
            case ["/session"]:
                self._console.info(str(self._session_id))
            case ["/history"]:
                snapshot = await self._client.session.get(session_id=self._session_id)
                self._replay(snapshot.items)
            case ["/cancel"]:
                await self._cancel_turn()
            case ["/events"]:
                self._trace = not self._trace
                self._console.info(f"event trace {'on' if self._trace else 'off'}")
            case _:
                self._console.warn(f"unknown command: {line}")
        return True

    async def _say(self, text: str) -> None:
        if self._turn_active and await self._steer(text):
            return
        await self._start_turn(text)

    async def _steer(self, text: str) -> bool:
        try:
            await self._client.turn.steer(
                session_id=self._session_id,
                message=text,
            )
        except RpcRemoteError as error:
            if error.code != _NO_ACTIVE_TURN:
                raise
            self._turn_finished()
            return False
        self._queued.append(text)
        self._console.trace("queued — delivered at the next tool call")
        return True

    async def _start_turn(self, text: str) -> None:
        self._turn_active = True
        self._update_hint()
        try:
            await self._client.turn.start(session_id=self._session_id, message=text)
        except RpcRemoteError:
            self._turn_finished()
            raise

    async def _flush_queued(self) -> None:
        if not self._queued:
            return
        text = "\n".join(self._queued)
        self._queued.clear()
        self._console.trace("the turn ended first — sending the queued message")
        await self._start_turn(text)

    async def _pump_events(self) -> None:
        try:
            async for notification in self._client.notifications():
                await self._handle(notification.params)
        except Exception as error:
            self._console.error(f"event stream stopped: {error}")
        else:
            self._console.warn("gateway connection closed")
        self._keyboard.stop()

    async def _handle(self, event: SessionEvent) -> None:
        if self._trace:
            self._console.trace(f"{event.type} #{event.sequence}")
        else:
            self._render(event)
        match event:
            case TurnStarted():
                self._turn_active = True
                self._update_hint()
            case TurnSteered(text=text):
                if text in self._queued:
                    self._queued.remove(text)
            case TurnCompleted() | TurnCancelled() | TurnFailed():
                self._turn_finished()
                await self._flush_queued()

    def _render(self, event: SessionEvent) -> None:
        match event:
            case TurnStarted():
                self._console.trace("turn started")
            case ChatDelta(text=text):
                if not self._streaming:
                    self._console.assistant_prefix()
                    self._streaming = True
                self._console.write(text)
            case ChatCompleted(finish_reason=reason):
                self._end_stream()
                self._console.trace(f"chat completed ({reason})")
            case TurnSteered(text=text):
                self._end_stream()
                self._console.trace(f"steering delivered: {_truncate(text)}")
            case ToolCallStarted(name=name, arguments=arguments):
                self._end_stream()
                self._console.tool(f"→ {name}({_format_arguments(arguments)})")
            case ToolCallCompleted(name=name, is_error=True, result=result):
                self._console.error(f"✗ {name}: {_truncate(str(result))}")
            case ToolCallCompleted(name=name, result=result):
                self._console.tool(f"✓ {name}: {_truncate(str(result))}")
            case TurnCompleted():
                self._end_stream()
            case TurnCancelled():
                self._end_stream()
                self._console.warn("turn cancelled")
            case TurnFailed(code=code, message=message):
                self._end_stream()
                self._console.error(f"turn failed [{code}] {message}")

    def _replay(self, items: list[Item]) -> None:
        for item in items:
            match item:
                case UserMessageItem(content=content):
                    self._console.user(content)
                case AssistantMessageItem(content=content):
                    self._console.assistant_prefix()
                    self._console.write(content)
                    self._console.newline()
                case ToolCallItem(name=name, status=status):
                    marker = "✗" if status is ToolCallStatus.FAILED else "✓"
                    self._console.tool(f"{marker} {name}")

    def _turn_finished(self) -> None:
        self._turn_active = False
        self._update_hint()

    def _update_hint(self) -> None:
        self._console.set_hint(_BUSY_HINT if self._turn_active else _IDLE_HINT)

    def _end_stream(self) -> None:
        if self._streaming:
            self._streaming = False
            self._console.newline()


def _format_arguments(arguments: dict[str, object]) -> str:
    return _truncate(", ".join(f"{key}={value!r}" for key, value in arguments.items()))


def _truncate(text: str, limit: int = 80) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 1]}…"
