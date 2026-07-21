import logging
import re
import shlex
from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from functools import partial
from typing import Any, Protocol

from cara.file_system import PathOutsideWorkspaceError, Workspace
from cara.tools.di import ToolContext
from cara.tools.params import AccessMode, BashParams, EditFileParams, PathField, ToolParams, WriteFileParams
from cara.tools.views import ActionResult, Tool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolCall:
    tool: Tool
    params: ToolParams | None
    raw_args: dict[str, Any]
    context: ToolContext


type ToolHandler = Callable[[ToolCall], Awaitable[ActionResult]]


class ToolMiddleware(Protocol):
    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult: ...


def compose(middlewares: Sequence[ToolMiddleware], terminal: ToolHandler) -> ToolHandler:
    handler = terminal
    for middleware in reversed(middlewares):
        handler = partial(middleware, next=handler)
    return handler


class ToolFeedbackError(Exception):
    """Expected tool failure whose message is safe and useful for the model."""


class ErrorBoundaryMiddleware:
    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        try:
            return await next(call)
        except ToolFeedbackError as error:
            return ActionResult.fail(error)
        except Exception:
            logger.exception("Tool '%s' failed", call.tool.name)
            return ActionResult.fail("Internal tool error.")


class ResultLimitMiddleware:
    def __init__(self, max_chars: int = 20_000) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        self._max_chars = max_chars

    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        result = await next(call)
        if result.ok and result.content is not None and len(result.content) > self._max_chars:
            return result.truncated(self._max_chars, note="Output truncated.")
        return result


def extract_paths(params: ToolParams) -> Iterator[tuple[str, AccessMode]]:
    for name, field in type(params).model_fields.items():
        for metadata in field.metadata:
            if isinstance(metadata, PathField):
                yield getattr(params, name), metadata.mode


@dataclass(frozen=True)
class PolicyDenial:
    message: str
    hint: str | None = None

    def feedback(self) -> str:
        return f"{self.message} {self.hint}" if self.hint else self.message


class PathPolicy:
    def __init__(
        self,
        *,
        allowed: Sequence[str] = (),
        denied: Sequence[str] = (),
    ) -> None:
        self._allowed = tuple(allowed)
        self._denied = tuple(denied)

    def check(self, path: str, mode: AccessMode, workspace: Workspace) -> PolicyDenial | None:
        del mode
        try:
            resolved = workspace.resolve(path)
        except PathOutsideWorkspaceError:
            return PolicyDenial(
                f"Path {path!r} is outside the workspace.",
                "Use a relative path below the workspace root.",
            )

        relative = resolved.relative_to(workspace.root).as_posix() or "."
        comparable = relative.casefold()
        if any(fnmatchcase(comparable, pattern.casefold()) for pattern in self._denied):
            return PolicyDenial(
                f"Path {path!r} is blocked by the workspace path policy.",
                "Choose a path that is not on the deny list.",
            )
        if self._allowed and not any(fnmatchcase(comparable, pattern.casefold()) for pattern in self._allowed):
            return PolicyDenial(
                f"Path {path!r} is not allowed by the workspace path policy.",
                f"Allowed patterns: {', '.join(self._allowed)}.",
            )
        return None


class PathPolicyMiddleware:
    def __init__(self, policy: PathPolicy) -> None:
        self._policy = policy

    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        if call.params is None:
            return await next(call)

        paths = tuple(extract_paths(call.params))
        if not paths:
            return await next(call)

        workspace = call.context.resolve(Workspace)
        if workspace is None:
            return ActionResult.fail(
                "The tool call contains a path, but no workspace is configured. "
                "Configure a Workspace before using file tools."
            )

        for path, mode in paths:
            denial = self._policy.check(path, mode, workspace)
            if denial is not None:
                return ActionResult.fail(denial.feedback())
        return await next(call)


class ContentSizeMiddleware:
    def __init__(self, max_bytes: int = 1_000_000) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._max_bytes = max_bytes

    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        content: str | None = None
        if isinstance(call.params, WriteFileParams):
            content = call.params.content
        elif isinstance(call.params, EditFileParams):
            content = call.params.new_text

        if content is not None and len(content.encode("utf-8")) > self._max_bytes:
            return ActionResult.fail(
                f"The requested file content exceeds the {self._max_bytes}-byte write limit. Write a smaller change."
            )
        return await next(call)


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


class BashPolicyMiddleware:
    def __init__(self, policy: BashPolicy) -> None:
        self._policy = policy

    async def __call__(self, call: ToolCall, next: ToolHandler) -> ActionResult:
        if isinstance(call.params, BashParams):
            denial = self._policy.check(call.params.command)
            if denial is not None:
                return ActionResult.fail(denial.feedback())
        return await next(call)
