import asyncio
import json
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping

_EXIT_COMMANDS = frozenset({"/exit", "/quit", "exit", "quit"})
_RESET = "\x1b[0m"
_BOLD_CYAN = "\x1b[1;36m"
_BOLD_MAGENTA = "\x1b[1;35m"
_DIM = "\x1b[2m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"


class TerminalRenderer:
    """Renders assistant text, tool calls, and notices to a terminal."""

    def __init__(
        self,
        *,
        output_writer: Callable[[str], None] = print,
        stream_writer: Callable[[str], None] | None = None,
        color: bool | None = None,
    ) -> None:
        self._output_writer = output_writer
        self._stream_writer = (
            _write_to_stdout if stream_writer is None else stream_writer
        )
        self._color = sys.stdout.isatty() if color is None else color
        self._response_open = False

    def style(self, text: str, style: str) -> str:
        if not self._color:
            return text
        return f"{style}{text}{_RESET}"

    def show_text_delta(self, delta: str) -> None:
        if not self._response_open:
            self._stream_writer(self.style("cara ❯ ", _BOLD_MAGENTA))
            self._response_open = True
        self._stream_writer(delta)

    def finish_response(self) -> None:
        if self._response_open:
            self._stream_writer("\n")
            self._response_open = False

    def show_tool_call(self, name: str, arguments: Mapping[str, object]) -> None:
        self.finish_response()
        rendered_arguments = json.dumps(
            dict(arguments), ensure_ascii=False, indent=2, sort_keys=True
        )
        lines = [self.style(f"╭─ tool  {name}", _BOLD_CYAN)]
        lines.extend(
            self.style(f"│  {line}", _DIM) for line in rendered_arguments.splitlines()
        )
        self._output_writer("\n".join(lines))

    def show_tool_result(self, name: str, content: str) -> None:
        lines = [self.style(f"╰─ done  {name}", _GREEN)]
        lines.extend(
            self.style(f"   {line}", _DIM)
            for line in (content.splitlines() or ["(no output)"])
        )
        self._output_writer("\n".join(lines))

    def show_tool_error(self, name: str, content: str) -> None:
        lines = [self.style(f"╰─ failed  {name}", _YELLOW)]
        lines.extend(
            self.style(f"   {line}", _DIM)
            for line in (content.splitlines() or ["(no output)"])
        )
        self._output_writer("\n".join(lines))

    def show_notice(self, text: str) -> None:
        self.finish_response()
        self._output_writer(self.style(text, _DIM))


class TurnRunner(ABC):
    """Executes a single user turn and renders it to the terminal."""

    @abstractmethod
    async def run_turn(self, text: str, renderer: TerminalRenderer) -> None: ...

    async def on_session_started(self, renderer: TerminalRenderer) -> None:
        return None

    async def on_user_turn_started(self) -> None:
        return None

    async def on_session_ended(self) -> None:
        return None


class TerminalSession:
    """Runs a text conversation through a terminal."""

    def __init__(
        self,
        runner: TurnRunner,
        *,
        prompt: str = "you  ❯ ",
        input_reader: Callable[[str], str] = input,
        renderer: TerminalRenderer | None = None,
    ) -> None:
        self._runner = runner
        self._prompt = prompt
        self._input_reader = input_reader
        self._renderer = TerminalRenderer() if renderer is None else renderer

    async def run(self) -> None:
        """Process terminal input until EOF or an explicit exit command."""
        await self._runner.on_session_started(self._renderer)
        try:
            while True:
                await self._runner.on_user_turn_started()
                try:
                    text = await asyncio.to_thread(
                        self._input_reader,
                        self._renderer.style(self._prompt, _BOLD_CYAN),
                    )
                except EOFError:
                    return

                text = text.strip()
                if text.lower() in _EXIT_COMMANDS:
                    return
                if not text:
                    continue

                try:
                    await self._runner.run_turn(text, self._renderer)
                finally:
                    self._renderer.finish_response()
        finally:
            await self._runner.on_session_ended()


def _write_to_stdout(text: str) -> None:
    print(text, end="", flush=True)
