import asyncio
from uuid import UUID

from pyrpckit.client import RpcRemoteError

from cli import commands
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

_IDLE_HINT = "type a message · / for commands · tab completes"
_BUSY_HINT = "type to steer · esc to interrupt"

# Padded to the same column `commands.help_text` aligns its summaries to.
_KEYS = """\
enter     send, or queue a steering message while a turn runs
tab       complete the command being typed, again to walk the matches
esc       clear the input, or interrupt the running turn\
"""

# Enough of a tool result to see what happened, not enough to bury the chat.
_RESULT_LINES = 4
_HEADLINE_LIMIT = 100
_VALUE_LIMIT = 60


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
        self._console.field("channel", self._channel.name)
        self._console.field("session", str(session_id))
        self._console.blank()
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
                case ControlKey.COMPLETE:
                    self._console.complete()
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
        command = commands.find(line.split()[0])
        if command is None:
            self._console.warn(f"unknown command: {line}")
            return True
        match command.name:
            case "/quit":
                return False
            case "/help":
                self._console.info(f"{_KEYS}\n\n{commands.help_text()}")
            case "/new":
                await self._create()
            case "/session":
                self._console.info(str(self._session_id))
            case "/history":
                snapshot = await self._client.session.get(session_id=self._session_id)
                self._replay(snapshot.items)
            case "/cancel":
                await self._cancel_turn()
            case "/events":
                self._trace = not self._trace
                self._console.info(f"event trace {'on' if self._trace else 'off'}")
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
                self._console.tool_call(name, _headline(arguments))
            case ToolCallCompleted(result=result, is_error=is_error):
                self._console.tool_result(_result_lines(result), failed=is_error)
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
                case ToolCallItem(
                    name=name,
                    arguments=arguments,
                    status=status,
                    result=result,
                    error=error,
                ):
                    self._console.tool_call(name, _headline(arguments))
                    self._replay_result(status, result, error)

    def _replay_result(
        self, status: ToolCallStatus, result: object, error: str | None
    ) -> None:
        """A stored call, minus the pending ones - those have nothing to show yet."""
        match status:
            case ToolCallStatus.FAILED:
                self._console.tool_result(_result_lines(error), failed=True)
            case ToolCallStatus.COMPLETED:
                self._console.tool_result(_result_lines(result), failed=False)
            case ToolCallStatus.PENDING:
                pass

    def _turn_finished(self) -> None:
        self._turn_active = False
        self._update_hint()

    def _update_hint(self) -> None:
        self._console.set_hint(_BUSY_HINT if self._turn_active else _IDLE_HINT)

    def _end_stream(self) -> None:
        if self._streaming:
            self._streaming = False
            self._console.newline()


def _headline(arguments: dict[str, object]) -> str:
    """What a call ran on, in one line.

    The first argument carries the call - a path, a query, a command - so it
    is shown bare and the rest stay named behind it.
    """
    if not arguments:
        return ""
    (_, subject), *rest = arguments.items()
    named = ", ".join(f"{key}={_value(value)}" for key, value in rest)
    parts = [_value(subject), *([named] if named else [])]
    return _truncate(" · ".join(parts), _HEADLINE_LIMIT)


def _result_lines(result: object) -> list[str]:
    """The head of a tool result, kept to a few lines with the rest counted."""
    text = result if isinstance(result, str) else repr(result)
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return []
    visible = [_truncate(line) for line in lines[:_RESULT_LINES]]
    hidden = len(lines) - len(visible)
    return visible + [f"+{hidden} more lines"] if hidden else visible


def _value(value: object) -> str:
    """A string argument reads better bare; anything else needs its repr."""
    return _truncate(value if isinstance(value, str) else repr(value), _VALUE_LIMIT)


def _truncate(text: str, limit: int = 80) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 1]}…"
