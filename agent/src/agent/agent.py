import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from agenttoolkit import Skills
from llmify import (
    ChatModel,
    LLMifyError,
    OpenAIResponsesStreamEnd,
    StreamEnd,
    StreamTextDelta,
    ToolCall,
    ToolResultMessage,
)

from agent.messages import MessageManager
from agent.prompt import SystemPrompt
from agent.tools import AgentTools
from voice.llm.events import (
    AgentEvent,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
)

type _EventQueue = asyncio.Queue[AgentEvent | _Failure]


class Agent:
    """Runs the tool-calling agent loop as a voice ``AgentSession`` implementation.

    ``voice.llm.port.AgentSession`` is a structural protocol, so it is
    deliberately not imported or subclassed here.
    """

    def __init__(
        self,
        *,
        llm: ChatModel,
        tools: AgentTools,
        skills: Skills | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._context = MessageManager(
            SystemPrompt(system_prompt=system_prompt, skills=skills)
        )
        self._turn: asyncio.Task[None] | None = None
        self._tool_preparation: asyncio.Task[None] | None = None
        self._tool_lifecycle = asyncio.Lock()

    async def prepare_turn(self) -> None:
        async with self._tool_lifecycle:
            if self._tool_preparation is None:
                self._tool_preparation = asyncio.create_task(
                    self._tools.prepare(),
                    name="agent-tools-prepare",
                )
            await asyncio.shield(self._tool_preparation)

    async def finish_turn(self) -> None:
        async with self._tool_lifecycle:
            preparation, self._tool_preparation = self._tool_preparation, None
            if preparation is None:
                return
            try:
                await asyncio.shield(preparation)
            finally:
                await self._tools.aclose()

    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        await self.prepare_turn()
        self._context.add_user(text)
        return self._stream_turn()

    async def steer(self, text: str) -> None:
        self._context.add_user(text)

    async def interrupt(self) -> None:
        await self._cancel_turn()
        await self.finish_turn()

    async def _stream_turn(self) -> AsyncIterator[AgentEvent]:
        events: _EventQueue = asyncio.Queue()
        self._turn = asyncio.create_task(self._run_turn(events))
        try:
            while True:
                event = await events.get()
                if isinstance(event, _Failure):
                    raise event.error
                yield event
                if isinstance(event, TurnCompleted):
                    return
        finally:
            await self._cancel_turn()
            await self.finish_turn()

    async def _run_turn(self, events: _EventQueue) -> None:
        try:
            await self._run_loop(events)
        except Exception as error:
            await events.put(_Failure(error))

    async def _cancel_turn(self) -> None:
        turn, self._turn = self._turn, None
        if turn is None:
            return
        turn.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await turn

    async def _run_loop(self, events: _EventQueue) -> None:
        while True:
            end = await self._stream_completion(events)
            completion = end.completion or ""

            if not end.tool_calls:
                self._context.add_assistant(completion)
                await events.put(TurnCompleted())
                return

            tool_results = await self._execute_tools(end.tool_calls, events)
            self._context.add_tool_round(completion, end.tool_calls, tool_results)

    async def _stream_completion(
        self, events: _EventQueue
    ) -> StreamEnd | OpenAIResponsesStreamEnd:
        end: StreamEnd | OpenAIResponsesStreamEnd | None = None
        async for event in self._llm.stream(
            self._context.to_llm_messages(), tools=self._tools.get_schema("openai")
        ):
            if isinstance(event, StreamTextDelta) and event.delta:
                await events.put(TextDelta(event.delta))
            elif isinstance(event, (StreamEnd, OpenAIResponsesStreamEnd)):
                end = event

        if end is None:
            raise LLMifyError("The model stream ended without a terminal event.")
        return end

    async def _execute_tools(
        self, tool_calls: list[ToolCall], events: _EventQueue
    ) -> list[ToolResultMessage]:
        results: list[ToolResultMessage] = []
        for tool_call in tool_calls:
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            await events.put(ToolStarted(name))
            result = await self._tools.execute(name, arguments)
            await events.put(ToolCompleted(name))
            content = "Tool completed successfully." if result is None else str(result)
            results.append(
                ToolResultMessage(tool_call_id=tool_call.id, content=content)
            )
        return results


@dataclass(frozen=True, slots=True)
class _Failure:
    error: Exception
