from agenttoolkit import Inject, Skills, Tools, requires
from pydantic import Field

from agent.tools.middleware import ToolError
from agent.tools.params import ToolParams


class LoadSkillParams(ToolParams):
    name: str = Field(description="Name of the skill to load, exactly as listed.")


def register_skill_tools(tools: Tools) -> None:
    @tools.action(
        description=(
            "Load a skill's full instructions into context before carrying "
            "out a task it covers. Call this first whenever a request matches "
            "one of the listed skills."
        ),
        params=LoadSkillParams,
        available_when=requires(Skills, predicate=lambda skills: len(skills) > 0),
    )
    async def load_skill(params: LoadSkillParams, skills: Inject[Skills]) -> str:
        try:
            loaded = skills.load(params.name)
        except ValueError as error:
            raise ToolError(str(error)) from None
        return loaded.instructions
