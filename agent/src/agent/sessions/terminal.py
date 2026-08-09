import asyncio
import json
import sys
from collections.abc import Callable

from transitbus import EventBus

from agent.agent import Agent
from agent.events import SessionEnded, SessionStarted, UserTurnStarted

_EXIT_COMMANDS = frozenset({"/exit", "/quit"})
_RESET = "\x1b[0m"
_BOLD_CYAN = "\x1b[1;36m"
_BOLD_MAGENTA = "\x1b[1;35m"
_DIM = "\x1b[2m"
_GREEN = "\x1b[32m"


def _write_to_stdout(text: str) -> None:
    print(text, end="", flush=True)


class TerminalSession:
    """Runs a text conversation through a terminal."""

    def __init__(
        self,
        agent: Agent,
        *,
        prompt: str = "you  \u276f ",
        input_reader: Callable[[str], str] = input,
        output_writer: Callable[[str], None] = print,
        stream_writer: Callable[[str], None] = _write_to_stdout,
        color: bool | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._agent = agent
        self._prompt = prompt
        self._input_reader = input_reader
        self._output_writer = output_writer
        self._stream_writer = stream_writer
        self._color = sys.stdout.isatty() if color is None else color
        self._response_open = False
        self._event_bus = event_bus

    async def run(self) -> None:
        """Process terminal input until EOF or an explicit exit command."""
        await self._dispatch(SessionStarted())
        try:
            while True:
                await self._dispatch(UserTurnStarted())
                try:
                    text = await asyncio.to_thread(
                        self._input_reader, self._style(self._prompt, _BOLD_CYAN)
                    )
                except EOFError:
                    return

                text = text.strip()
                if text in _EXIT_COMMANDS:
                    return
                if not text:
                    continue

                try:
                    await self._agent.respond(
                        text,
                        on_text_delta=self._show_text_delta,
                        on_tool_call=self._show_tool_call,
                        on_tool_result=self._show_tool_result,
                    )
                finally:
                    self._finish_response()
        finally:
            await self._dispatch(SessionEnded())

    async def _dispatch(
        self, event: SessionStarted | UserTurnStarted | SessionEnded
    ) -> None:
        if self._event_bus is not None:
            await self._event_bus.dispatch(event)

    def _show_text_delta(self, delta: str) -> None:
        if not self._response_open:
            self._stream_writer(self._style("cara \u276f ", _BOLD_MAGENTA))
            self._response_open = True
        self._stream_writer(delta)

    def _finish_response(self) -> None:
        if self._response_open:
            self._stream_writer("\n")
            self._response_open = False

    def _show_tool_call(self, name: str, arguments: dict[str, object]) -> None:
        self._finish_response()
        rendered_arguments = json.dumps(
            arguments, ensure_ascii=False, indent=2, sort_keys=True
        )
        lines = [self._style(f"\u256d\u2500 tool  {name}", _BOLD_CYAN)]
        lines.extend(
            self._style(f"\u2502  {line}", _DIM)
            for line in rendered_arguments.splitlines()
        )
        self._output_writer("\n".join(lines))

    def _show_tool_result(self, name: str, content: str) -> None:
        lines = [self._style(f"\u2570\u2500 done  {name}", _GREEN)]
        lines.extend(
            self._style(f"   {line}", _DIM)
            for line in (content.splitlines() or ["(no output)"])
        )
        self._output_writer("\n".join(lines))

    def _style(self, text: str, style: str) -> str:
        if not self._color:
            return text
        return f"{style}{text}{_RESET}"
