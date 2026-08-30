from agenttoolkit import Inject, Tools

from agent.clock import LocalClock


def register_time_tools(tools: Tools) -> None:
    @tools.tool(
        description=(
            "Get the current local date and time in the configured timezone. "
            "Call this whenever an answer or action depends on the current date "
            "or time; never infer it from model knowledge or the host clock."
        )
    )
    async def current_time(clock: Inject[LocalClock]) -> str:
        now = clock.now()
        return (
            f"Current local date and time: {now.isoformat(timespec='seconds')} "
            f"({clock.timezone}, {now:%Z})."
        )
