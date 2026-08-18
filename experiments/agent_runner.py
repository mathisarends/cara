from agent import Agent
from experiments.terminal import TerminalRenderer, TurnRunner


class AgentTurnRunner(TurnRunner):
    """Runs turns against an in-process agent."""

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    async def run_turn(self, text: str, renderer: TerminalRenderer) -> None:
        await self._agent.respond(
            text,
            on_text_delta=renderer.show_text_delta,
            on_tool_call=renderer.show_tool_call,
            on_tool_result=renderer.show_tool_result,
        )
