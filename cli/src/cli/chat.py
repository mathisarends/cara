import asyncio
from uuid import UUID

from cli.console import Console
from gateway_client import GatewayClient
from gateway_client.models import (
    AssistantMessageItem,
    ChatCompleted,
    ChatDelta,
    Item,
    SessionEvent,
    ToolCallCompleted,
    ToolCallItem,
    ToolCallStarted,
    ToolCallStatus,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
    UserMessageItem,
)

_HELP = """\
/new              start a fresh session
/session          show the current session id
/history          replay the session snapshot from the gateway
/events           toggle the raw event trace
/cancel           cancel the running turn
/quit             leave (ctrl-c works too)\
"""


class ChatSession:
    def __init__(self, client: GatewayClient, console: Console, trace: bool) -> None:
        self._client = client
        self._console = console
        self._trace = trace
        self._session_id: UUID | None = None
        self._turn_finished = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._streaming = False

    async def run(self, session_id: UUID | None) -> None:
        pump = asyncio.create_task(self._pump_events())
        try:
            await self._open(session_id)
            await self._prompt_loop()
        finally:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)

    async def _open(self, session_id: UUID | None) -> None:
        if session_id is None:
            session = await self._client.session.create(metadata={"client": "cara-cli"})
            self._session_id = session.id
            self._console.info(f"session {session.id} created")
        else:
            snapshot = await self._client.session.get(session_id=session_id)
            self._session_id = snapshot.session.id
            self._console.info(f"session {snapshot.session.id} resumed")
            self._replay(snapshot.items)
        await self._client.session.subscribe(session_id=self._session_id)
        self._console.info("subscribed — type a message, /help for commands")

    async def _prompt_loop(self) -> None:
        while not self._disconnected.is_set():
            line = (await asyncio.to_thread(input, self._console.prompt())).strip()
            if not line:
                continue
            if line.startswith("/"):
                if not await self._run_command(line):
                    return
                continue
            await self._send(line)

    async def _run_command(self, line: str) -> bool:
        match line.split():
            case ["/quit" | "/exit" | "/q"]:
                return False
            case ["/help" | "/h"]:
                self._console.info(_HELP)
            case ["/new"]:
                await self._open(None)
            case ["/session"]:
                self._console.info(str(self._session_id))
            case ["/history"]:
                snapshot = await self._client.session.get(session_id=self._session_id)
                self._replay(snapshot.items)
            case ["/events"]:
                self._trace = not self._trace
                self._console.info(f"event trace {'on' if self._trace else 'off'}")
            case ["/cancel"]:
                await self._client.turn.cancel(session_id=self._session_id)
            case _:
                self._console.warn(f"unknown command: {line}")
        return True

    async def _send(self, message: str) -> None:
        self._turn_finished.clear()
        await self._client.turn.start(session_id=self._session_id, message=message)
        finished = asyncio.create_task(self._turn_finished.wait())
        closed = asyncio.create_task(self._disconnected.wait())
        try:
            await asyncio.wait((finished, closed), return_when=asyncio.FIRST_COMPLETED)
        finally:
            finished.cancel()
            closed.cancel()

    async def _pump_events(self) -> None:
        async for notification in self._client.notifications():
            self._handle(notification.params)
        self._disconnected.set()
        self._turn_finished.set()
        self._console.warn("gateway connection closed")

    def _handle(self, event: SessionEvent) -> None:
        if self._trace:
            self._console.trace(f"{event.type} #{event.sequence}")
        else:
            self._render(event)
        if isinstance(event, TurnCompleted | TurnCancelled | TurnFailed):
            self._turn_finished.set()

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

    def _end_stream(self) -> None:
        if self._streaming:
            self._streaming = False
            self._console.newline()


def _format_arguments(arguments: dict[str, object]) -> str:
    return _truncate(", ".join(f"{key}={value!r}" for key, value in arguments.items()))


def _truncate(text: str, limit: int = 80) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 1]}…"
