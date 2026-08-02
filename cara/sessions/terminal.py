import asyncio
import json
from collections.abc import Callable

from cara.agent import Agent

_EXIT_COMMANDS = frozenset({"/exit", "/quit"})


class TerminalSession:
    """Runs a text conversation through a terminal."""

    def __init__(
        self,
        agent: Agent,
        *,
        prompt: str = "> ",
        input_reader: Callable[[str], str] = input,
        output_writer: Callable[[str], None] = print,
    ) -> None:
        self._agent = agent
        self._prompt = prompt
        self._input_reader = input_reader
        self._output_writer = output_writer

    async def run(self) -> None:
        """Process terminal input until EOF or an explicit exit command."""
        while True:
            try:
                text = await asyncio.to_thread(self._input_reader, self._prompt)
            except EOFError:
                return

            text = text.strip()
            if text in _EXIT_COMMANDS:
                return
            if not text:
                continue

            answer = await self._agent.respond(
                text,
                on_tool_call=self._show_tool_call,
                on_tool_result=self._show_tool_result,
            )
            if answer:
                self._output_writer(answer)

    def _show_tool_call(self, name: str, arguments: dict[str, object]) -> None:
        rendered_arguments = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        self._output_writer(f"[tool] {name} {rendered_arguments}")

    def _show_tool_result(self, name: str, content: str, ok: bool) -> None:
        label = "tool result" if ok else "tool error"
        self._output_writer(f"[{label}] {name}: {content}")
