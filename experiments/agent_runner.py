from transitbus import EventBus

from agent import Agent
from agent.events import SessionEnded, SessionStarted, UserTurnStarted
from experiments.terminal import TerminalRenderer, TurnRunner


class AgentTurnRunner(TurnRunner):
    """Runs turns against an in-process agent."""

    def __init__(self, agent: Agent, *, event_bus: EventBus | None = None) -> None:
        self._agent = agent
        self._event_bus = event_bus

    async def run_turn(self, text: str, renderer: TerminalRenderer) -> None:
        await self._agent.respond(
            text,
            on_text_delta=renderer.show_text_delta,
            on_tool_call=renderer.show_tool_call,
            on_tool_result=renderer.show_tool_result,
        )

    async def on_session_started(self, renderer: TerminalRenderer) -> None:
        await self._dispatch(SessionStarted())

    async def on_user_turn_started(self) -> None:
        await self._dispatch(UserTurnStarted())

    async def on_session_ended(self) -> None:
        await self._dispatch(SessionEnded())

    async def _dispatch(
        self, event: SessionStarted | UserTurnStarted | SessionEnded
    ) -> None:
        if self._event_bus is not None:
            await self._event_bus.dispatch(event)
