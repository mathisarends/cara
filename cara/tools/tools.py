import builtins
from collections.abc import Callable
from typing import Any

from cara.skills import Skill, SkillRepository
from cara.tools.di import Inject, ToolContext
from cara.tools.executor import ToolExecutor
from cara.tools.params import (
    EndSessionParams,
    LoadSkillParams,
    RemoveSkillParams,
    ToolParams,
)
from cara.tools.schemas import ToolSchema
from cara.tools.views import ActionKind, ActionResult, Tool


class Tools:
    def __init__(self, context: ToolContext | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._context = context if context is not None else ToolContext()
        self._executor = ToolExecutor(self._tools, self._context)
        self._loaded_skills: dict[str, Skill] = {}

        self._register_default_tools()

    def set_context(self, context: ToolContext) -> None:
        self._context = context
        self._executor.set_context(context)

    def provide(self, *dependencies: object) -> None:
        self._context.provide(*dependencies)

    def resolve[T](self, expected_type: type[T]) -> T | None:
        return self._context.resolve(expected_type)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def render_skill_context(self) -> str:
        """Skill section for the system prompt: the catalog plus loaded instructions."""
        sections: list[str] = []
        repository = self._context.resolve(SkillRepository)
        if repository is not None and (catalog := repository.render_catalog()):
            sections.append(f"# Available Skills\n\n{catalog}")
        if self._loaded_skills:
            loaded = "\n\n".join(f"## {skill.name}\n{skill.instructions}" for skill in self._loaded_skills.values())
            sections.append(f"# Active Skills\n\n{loaded}")
        return "\n\n".join(sections)

    def action[P: ToolParams](
        self,
        description: str | None = None,
        name: str | None = None,
        *,
        params: type[P] | None = None,
        kind: ActionKind = ActionKind.GENERIC,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._register(
                Tool(
                    name=name or fn.__name__,
                    description=description,
                    fn=fn,
                    param_model=params,
                    kind=kind,
                )
            )
            return fn

        return decorator

    def _register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    async def execute(self, name: str, args: dict[str, Any] | None = None) -> ActionResult:
        return await self._executor.execute(name, args)

    def to_schema(self) -> builtins.list[ToolSchema]:
        return [tool.to_schema() for tool in self._tools.values()]

    def _register_default_tools(self) -> None:
        self._register_end_session_tool()
        self._register_skill_tools()

    def _register_end_session_tool(self) -> None:
        @self.action(
            name="end_session",
            description=(
                "End the conversation when the user says goodbye or otherwise signals "
                "they are finished. Provide a short spoken farewell."
            ),
            params=EndSessionParams,
            kind=ActionKind.END_SESSION,
        )
        async def end_session(params: EndSessionParams) -> ActionResult:
            return ActionResult.success(params.farewell)

    def _register_skill_tools(self) -> None:
        @self.action(
            name="load_skill",
            description=(
                "Load a skill's full instructions into context before carrying out a "
                "task it covers. Call this first whenever a request matches one of the "
                "skills listed under 'Available Skills', then follow the loaded instructions."
            ),
            params=LoadSkillParams,
        )
        async def load_skill(params: LoadSkillParams, repository: Inject[SkillRepository]) -> ActionResult:
            skill = repository.get(params.name)
            if skill is None:
                available = ", ".join(repository.names())
                return ActionResult.fail(f"Unknown skill '{params.name}'. Available: {available}")
            self._loaded_skills[skill.name] = skill
            return ActionResult.success(f"Loaded skill '{skill.name}'.")

        @self.action(
            name="remove_skill",
            description=(
                "Remove a previously loaded skill from context once its task is done, to keep the context focused."
            ),
            params=RemoveSkillParams,
        )
        async def remove_skill(params: RemoveSkillParams) -> ActionResult:
            if self._loaded_skills.pop(params.name, None) is None:
                return ActionResult.fail(f"Skill '{params.name}' is not loaded.")
            return ActionResult.success(f"Removed skill '{params.name}'.")
