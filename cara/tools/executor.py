import inspect
import logging
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from cara.tools.di import ToolContext, _InjectMarker
from cara.tools.views import ActionResult, Tool

logger = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self, tools: dict[str, Tool], context: ToolContext) -> None:
        self._tools = tools
        self._context = context

    def set_context(self, context: ToolContext) -> None:
        self._context = context

    async def execute(self, name: str, args: dict[str, Any] | None = None) -> ActionResult:
        tool = self._tools.get(name)
        if tool is None:
            return ActionResult.fail(f"Unknown tool '{name}'. Available: {list(self._tools)}")

        try:
            resolved_args = self._resolve_args(tool, args or {})
        except Exception as error:
            logger.exception("Failed to resolve args for tool '%s'", name)
            return ActionResult.fail(error)

        return await tool.execute(resolved_args)

    def _resolve_args(self, tool: Tool, args: dict[str, Any]) -> dict[str, Any]:
        kwargs = self._resolve_non_injected_args(tool, args)
        hints = get_type_hints(tool.fn, include_extras=True)
        signature = inspect.signature(tool.fn)

        for param_name, param in signature.parameters.items():
            hint = hints.get(param_name)
            if hint is None or not self._is_injectable(hint):
                continue

            actual_type = get_args(hint)[0]
            dependency = self._context.resolve(actual_type)
            if dependency is None:
                if param.default is inspect.Parameter.empty:
                    raise ValueError(
                        f"Missing injected dependency for parameter '{param_name}' "
                        f"of type '{actual_type.__name__}'"
                    )
                continue
            kwargs[param_name] = dependency

        return kwargs

    def _resolve_non_injected_args(self, tool: Tool, args: dict[str, Any]) -> dict[str, Any]:
        if tool.param_model is None:
            return dict(args)

        model_instance = tool.param_model.model_validate(args)
        hints = get_type_hints(tool.fn, include_extras=True)
        signature = inspect.signature(tool.fn)
        target = self._find_param_model_parameter(
            signature=signature,
            hints=hints,
            param_model=tool.param_model,
        )
        if target is None:
            raise ValueError(
                f"Tool '{tool.name}' uses params model '{tool.param_model.__name__}' "
                "but function has no parameter that can receive it"
            )
        return {target: model_instance}

    def _find_param_model_parameter(
        self,
        signature: inspect.Signature,
        hints: dict[str, Any],
        param_model: type[BaseModel],
    ) -> str | None:
        candidates: list[str] = []
        for param_name in signature.parameters:
            if param_name in ("self", "cls"):
                continue
            hint = hints.get(param_name)
            if hint is not None and self._is_injectable(hint):
                continue
            candidates.append(param_name)
            if hint == param_model:
                return param_name

        if len(candidates) == 1:
            return candidates[0]
        return None

    @staticmethod
    def _is_injectable(hint: Any) -> bool:
        if get_origin(hint) is not Annotated:
            return False
        return any(isinstance(metadata, _InjectMarker) for metadata in get_args(hint))
