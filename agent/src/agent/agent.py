import asyncio
import contextlib
import json
from collections import deque
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from agenttoolkit import Skills

from agent.clock import LocalClock
from agent.events import (
    AgentEvent,
    SteeringApplied,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
)
from agent.messages import MessageManager
from agent.models import ModelSwitch
from agent.prompt import SystemPrompt
from agent.runtime import TurnFailure
from agent.tools import AgentTools, FatalToolError
from agent.tools.middleware import ToolFailure
from llm import (
    ChatModel,
    Message,
    ModelError,
    ModelResponse,
    ModelTool,
    ToolCall,
    ToolResultMessage,
)
from llm import (
    TextDelta as ModelTextDelta,
)

_EVENT_QUEUE_SIZE = 64

type _EventQueue = asyncio.Queue[AgentEvent | TurnFailure]


class Agent:
    """Runs one stateful tool-calling agent loop."""

    def __init__(
        self,
        *,
        models: ModelSwitch,
        tools: AgentTools,
        skills: Skills | None = None,
        clock: LocalClock | None = None,
        system_prompt: str | None = None,
        workspace_root: Path | None = None,
        messages: Sequence[Message] = (),
    ) -> None:
        self._models = models
        self._tools = tools
        selected_clock = clock or LocalClock()
        self._context = MessageManager(
            SystemPrompt(
                root=workspace_root,
                system_prompt=system_prompt,
                skills=skills,
                today=selected_clock.today,
            ),
            messages,
        )
        self._turn: asyncio.Task[None] | None = None
        self._turn_lock = asyncio.Lock()
        self._steering: deque[str] = deque()
        self._tool_preparation: asyncio.Task[None] | None = None
        self._tool_lifecycle = asyncio.Lock()
        self._tools_ready = False
        self._tools_closed = False

    @property
    def _llm(self) -> ChatModel:
        return self._models.current

    async def prepare_turn(self) -> None:
        async with self._tool_lifecycle:
            if self._tools_closed:
                raise RuntimeError("The agent is already closed.")
            if self._tools_ready:
                return
            if self._tool_preparation is None:
                self._tool_preparation = asyncio.create_task(
                    self._tools.prepare(),
                    name="agent-tools-prepare",
                )
            try:
                await asyncio.shield(self._tool_preparation)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._tool_preparation = None
                raise
            self._tool_preparation = None
            self._tools_ready = True

    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        async with self._turn_lock:
            if self._turn is not None and not self._turn.done():
                raise RuntimeError(
                    "A turn is already running; steer() or interrupt() first."
                )
            await self.prepare_turn()
            self._steering.clear()
            self._context.add_user(text)
            events: _EventQueue = asyncio.Queue(maxsize=_EVENT_QUEUE_SIZE)
            turn = asyncio.create_task(self._run_turn(events), name="agent-turn")
            self._turn = turn
            return self._stream_turn(events, turn)

    async def steer(self, text: str) -> None:
        """Queue text for the running turn.

        The loop picks it up at the next tool-call boundary, so the model sees it
        before deciding on its next step. Text that arrives after the last
        boundary is discarded when the next turn starts.
        """
        self._steering.append(text)

    async def interrupt(self) -> None:
        await self._cancel_turn()

    async def aclose(self) -> None:
        await self.interrupt()
        try:
            await self._close_tools()
        finally:
            await self._models.aclose()

    async def _stream_turn(
        self,
        events: _EventQueue,
        turn: asyncio.Task[None],
    ) -> AsyncIterator[AgentEvent]:
        try:
            while True:
                event = await events.get()
                if isinstance(event, TurnFailure):
                    raise event.error
                yield event
                if isinstance(event, TurnCompleted):
                    return
        finally:
            await self._cancel_turn(turn)

    async def _run_turn(self, events: _EventQueue) -> None:
        try:
            await self._run_loop(events)
        except Exception as error:
            await events.put(TurnFailure(error))

    async def _cancel_turn(self, expected: asyncio.Task[None] | None = None) -> None:
        turn = self._turn
        if turn is None:
            return
        if expected is not None and turn is not expected:
            return
        self._turn = None
        turn.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await turn

    async def _close_tools(self) -> None:
        async with self._tool_lifecycle:
            if self._tools_closed:
                return
            preparation, self._tool_preparation = self._tool_preparation, None
            try:
                if preparation is not None:
                    await asyncio.shield(preparation)
            finally:
                self._tools_ready = False
                self._tools_closed = True
                await self._tools.aclose()

    async def _run_loop(self, events: _EventQueue) -> None:
        response_parts: list[str] = []
        while True:
            end = await self._stream_completion(events)
            completion = end.completion
            response_parts.append(completion)

            if not end.tool_calls:
                self._context.add_assistant(completion)
                await events.put(
                    TurnCompleted(
                        text="".join(response_parts),
                        finish_reason=end.finish_reason,
                    )
                )
                return

            tool_results = await self._execute_tools(end.tool_calls, events)
            self._context.add_tool_round(
                completion,
                end.tool_calls,
                tool_results,
                provider_state=end.provider_state,
            )
            await self._apply_steering(events)

    async def _apply_steering(self, events: _EventQueue) -> None:
        while self._steering:
            text = self._steering.popleft()
            self._context.add_user(text)
            await events.put(SteeringApplied(text))

    async def _stream_completion(self, events: _EventQueue) -> ModelResponse:
        end: ModelResponse | None = None
        async for event in self._llm.stream(
            self._context.to_llm_messages(), tools=self._llm_tools()
        ):
            if isinstance(event, ModelTextDelta) and event.delta:
                await events.put(TextDelta(event.delta))
            elif isinstance(event, ModelResponse):
                end = event

        if end is None:
            raise ModelError("The model stream ended without a terminal event.")
        return end

    async def _execute_tools(
        self, tool_calls: Sequence[ToolCall], events: _EventQueue
    ) -> list[ToolResultMessage]:
        results: list[ToolResultMessage] = []
        for tool_call in tool_calls:
            name = tool_call.name
            arguments, parse_error = _try_parse_tool_arguments(tool_call)
            await events.put(ToolStarted(name, tool_call.id, arguments))

            if parse_error is not None:
                result = ToolFailure(_error_content(parse_error))
            else:
                result = await self._execute_tool(name, arguments)

            is_error = isinstance(result, ToolFailure)
            await events.put(
                ToolCompleted(name, tool_call.id, result, is_error=is_error)
            )
            content = "Tool completed successfully." if result is None else str(result)
            results.append(
                ToolResultMessage(
                    tool_call_id=tool_call.id,
                    tool_name=name,
                    content=content,
                    is_error=is_error,
                )
            )
        return results

    async def _execute_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> object:
        try:
            return await self._tools.execute(name, arguments)
        except FatalToolError:
            raise
        except Exception as error:
            return ToolFailure(_error_content(error))

    def _llm_tools(self) -> list[ModelTool]:
        return [
            ModelTool(
                name=schema.name,
                description=schema.description,
                parameters=schema.parameters,
            )
            for schema in self._tools.get_schema()
        ]


def _try_parse_tool_arguments(
    tool_call: ToolCall,
) -> tuple[dict[str, object], Exception | None]:
    try:
        arguments = json.loads(tool_call.arguments or "{}")
        if not isinstance(arguments, dict):
            raise ValueError(f"Tool arguments for '{tool_call.name}' must be an object")
    except Exception as error:
        return {}, error
    return arguments, None


def _error_content(error: Exception) -> str:
    message = str(error)
    if message:
        return f"{type(error).__name__}: {message}"
    return type(error).__name__
