import re
import shlex
from collections.abc import Sequence

from cara.tools.middleware.base import ToolCall, ToolHandler, ToolMiddleware
from cara.tools.middleware.path_policy import PolicyDenial
from cara.tools.params import BashParams
from cara.tools.views import ActionResult


class BashPolicy:
    """Allow configured simple command prefixes, never arbitrary shell programs."""

    _shell_syntax = re.compile(r"[;&|<>`$()\r\n]")

    def __init__(self, allowed_commands: Sequence[str] = ()) -> None:
        self._allowed_prefixes = tuple(tuple(shlex.split(command)) for command in allowed_commands)
        if any(not prefix for prefix in self._allowed_prefixes):
            raise ValueError("allowed Bash command prefixes must not be empty")

    def check(self, command: str) -> PolicyDenial | None:
        command = command.strip()
        if not self._allowed_prefixes:
            return PolicyDenial(
                "Bash execution is disabled by the current tool policy.",
                "Use the dedicated file tools or configure an explicit command allow-list.",
            )
        if self._shell_syntax.search(command):
            return PolicyDenial(
                "Shell operators, redirects, substitutions, and command chaining are not allowed.",
                "Run one allow-listed command without shell syntax.",
            )

        try:
            arguments = tuple(shlex.split(command))
        except ValueError as error:
            return PolicyDenial(f"The Bash command could not be parsed: {error}")

        if any(arguments[: len(prefix)] == prefix for prefix in self._allowed_prefixes):
            return None

        allowed = ", ".join(shlex.join(prefix) for prefix in self._allowed_prefixes)
        command_name = repr(arguments[0] if arguments else command)
        return PolicyDenial(
            f"Command {command_name} is not allowed.",
            f"Allowed command prefixes: {allowed}.",
        )


class BashPolicyMiddleware(ToolMiddleware):
    def __init__(self, policy: BashPolicy) -> None:
        self._policy = policy

    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        if isinstance(call.params, BashParams):
            denial = self._policy.check(call.params.command)
            if denial is not None:
                return ActionResult.fail(denial.feedback())
        return await next(call)
