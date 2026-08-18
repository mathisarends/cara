from agent import Agent
from experiments.terminal import TerminalRenderer, TurnRunner
from voice.llm import TextDelta, ToolCompleted, ToolStarted, TurnCompleted


class AgentTurnRunner(TurnRunner):
    """Runs turns against an in-process agent."""

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    async def on_user_turn_started(self) -> None:
        await self._agent.prepare_turn()

    async def run_turn(self, text: str, renderer: TerminalRenderer) -> None:
        events = await self._agent.start_turn(text)
        async for event in events:
            match event:
                case TextDelta(text=text) if text:
                    renderer.show_text_delta(text)
                case ToolStarted(name=name):
                    renderer.show_tool_call(name, {})
                case ToolCompleted(name=name):
                    renderer.show_tool_result(name, "completed")
                case TurnCompleted():
                    return
                case TextDelta():
                    pass

    async def on_session_ended(self) -> None:
        await self._agent.finish_turn()
