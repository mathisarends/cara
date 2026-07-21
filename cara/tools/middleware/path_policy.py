from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase

from cara.file_system import PathOutsideWorkspaceError, Workspace
from cara.tools.middleware.base import ToolCall, ToolHandler, ToolMiddleware
from cara.tools.params import AccessMode, PathField, ToolParams
from cara.tools.views import ActionResult


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
    _DEFAULT_DENIED = (
        ".env",
        "**/.env",
        ".git",
        ".git/**",
        "**/.git/**",
        "*.pem",
        "**/*.pem",
        "id_rsa*",
        "**/id_rsa*",
    )

    def __init__(
        self,
        *,
        allowed: Sequence[str] = (),
        denied: Sequence[str] | None = None,
    ) -> None:
        self._allowed = tuple(allowed)
        self._denied = tuple(denied) if denied is not None else self._DEFAULT_DENIED

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


class PathPolicyMiddleware(ToolMiddleware):
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
