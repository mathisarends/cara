from collections.abc import Sequence

from cara.tools.middleware.base import ToolCall, ToolHandler, ToolMiddleware
from cara.tools.middleware.path_policy import PolicyDenial
from cara.tools.params import BashParams
from cara.tools.views import ActionResult


class BashPolicy:
    """Temporarily allow all Bash commands without an allow-list."""

    def __init__(self, allowed_commands: Sequence[str] = ()) -> None:
        pass

    def check(self, command: str) -> PolicyDenial | None:
        return None


class BashPolicyMiddleware(ToolMiddleware):
    def __init__(self, allowed_commands: Sequence[str] = ()) -> None:
        self._policy = BashPolicy(allowed_commands)

    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        if isinstance(call.params, BashParams):
            denial = self._policy.check(call.params.command)
            if denial is not None:
                return ActionResult.fail(denial.feedback())
        return await next(call)
