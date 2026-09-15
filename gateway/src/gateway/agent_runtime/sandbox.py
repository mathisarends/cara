import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

import httpx2
from agenttoolkit.builtins import CommandResult
from agenttoolkit.builtins.fs import Entry, GrepMatch
from agenttoolkit.builtins.shell import DEFAULT_TIMEOUT, CommandTimeout
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr

from sandbox_manager_client import (
    ApiError,
    ExecRequest,
    FileEditRequest,
    FileNotFoundProblem,
    FileWriteRequest,
    GrepRequest,
    InvalidEditProblem,
    InvalidWorkspaceIdProblem,
    NotADirectoryProblem,
    PathOutsideWorkspaceProblem,
    SandboxManagerClient,
    StdinNotSupportedProblem,
)
from sandbox_manager_client import FileEntry as GeneratedEntry
from sandbox_manager_client import FileMatch as GeneratedMatch


class SandboxClientSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8081")
    token: SecretStr = SecretStr("change-me")
    workspace_id: str = Field(default="default", min_length=1)


class WorkspaceSandboxClient:
    def __init__(
        self,
        settings: SandboxClientSettings,
        root: Path,
        client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._root = root
        self._authorization = f"Bearer {settings.token.get_secret_value()}"
        self._owns_client = client is None
        self._http_client = client or httpx2.AsyncClient()
        self._client = SandboxManagerClient(
            self._http_client, str(settings.url).rstrip("/")
        )

    @property
    def root(self) -> Path:
        return self._root

    async def ensure(self) -> None:
        async with _translate_errors():
            await self._client.ensure_sandbox(self._workspace_id, self._authorization)

    async def execute(
        self,
        command: str,
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        stdin: str | bytes | None = None,
        timeout: CommandTimeout = DEFAULT_TIMEOUT,
    ) -> CommandResult:
        started = time.perf_counter()
        timeout_seconds = 15 if timeout in (DEFAULT_TIMEOUT, None) else timeout
        async with _translate_errors():
            result = await self._client.execute(
                self._workspace_id,
                self._authorization,
                ExecRequest(
                    argv=["/bin/bash", "-lc", command],
                    cwd=_container_cwd(cwd),
                    env=dict(env or {}),
                    stdin=stdin.decode() if isinstance(stdin, bytes) else stdin,
                    timeout_seconds=timeout_seconds,
                ),
                timeout=timeout_seconds + 5,
            )
        return CommandResult(
            command=command,
            returncode=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=time.perf_counter() - started,
            timed_out=result.timed_out,
        )

    async def read_file(self, path: str | Path, *, encoding: str | None = None) -> str:
        _require_utf8(encoding)
        async with _translate_errors():
            return await self._client.read_file(
                self._workspace_id, _path(path), self._authorization
            )

    async def write_file(
        self,
        path: str | Path,
        content: str,
        *,
        encoding: str | None = None,
        create_parents: bool = True,
    ) -> None:
        _require_utf8(encoding)
        if not create_parents:
            raise ValueError("remote workspace always creates parent directories")
        async with _translate_errors():
            await self._client.write_file(
                self._workspace_id,
                _path(path),
                self._authorization,
                FileWriteRequest(content=content),
            )

    async def edit_file(
        self,
        path: str | Path,
        old: str,
        new: str,
        *,
        replace_all: bool = False,
        encoding: str | None = None,
    ) -> int:
        _require_utf8(encoding)
        async with _translate_errors():
            response = await self._client.edit_file(
                self._workspace_id,
                _path(path),
                self._authorization,
                FileEditRequest(old=old, new=new, replace_all=replace_all),
            )
        return response.count

    async def list_dir(
        self,
        path: str | Path = ".",
        *,
        recursive: bool = False,
        limit: int | None = None,
    ) -> list[Entry]:
        async with _translate_errors():
            entries = await self._client.list_entries(
                self._workspace_id,
                self._authorization,
                directory=str(path),
                recursive=recursive,
            )
        result = [_entry(item) for item in entries]
        return result if limit is None else result[:limit]

    async def glob(self, pattern: str) -> list[Entry]:
        async with _translate_errors():
            entries = await self._client.glob_files(
                self._workspace_id, pattern, self._authorization
            )
        return [_entry(item) for item in entries]

    async def grep(
        self,
        pattern: str,
        *,
        glob: str | None = None,
        case_sensitive: bool = True,
        context_lines: int = 0,
        max_matches: int | None = None,
    ) -> list[GrepMatch]:
        async with _translate_errors():
            matches = await self._client.grep_files(
                self._workspace_id,
                self._authorization,
                GrepRequest(
                    pattern=pattern,
                    glob=glob,
                    case_sensitive=case_sensitive,
                    context_lines=context_lines,
                    max_matches=max_matches,
                ),
            )
        return [_match(item) for item in matches]

    async def stat(self, path: str | Path) -> Entry | None:
        async with _translate_errors():
            entry = await self._client.stat_file(
                self._workspace_id, _path(path), self._authorization
            )
        return None if entry is None else _entry(entry)

    async def aclose(self) -> None:
        await self._client.aclose()
        if self._owns_client:
            await self._http_client.aclose()

    @property
    def _workspace_id(self) -> str:
        return self._settings.workspace_id


def _path(path: str | Path) -> str:
    text = str(path).replace("\\", "/").lstrip("/")
    return quote(text, safe="/")


def _container_cwd(cwd: str | Path | None) -> str:
    if cwd is None:
        return "/workspace"
    text = str(cwd).replace("\\", "/")
    if text.startswith("/workspace"):
        return text
    return f"/workspace/{text.lstrip('./')}"


def _require_utf8(encoding: str | None) -> None:
    if encoding is not None and encoding.lower().replace("-", "") != "utf8":
        raise ValueError("remote workspace supports UTF-8 only")


def _entry(item: GeneratedEntry) -> Entry:
    return Entry(
        path=item.path,
        is_dir=item.is_dir,
        is_symlink=item.is_symlink,
        size=item.size,
        modified=item.modified,
    )


def _match(item: GeneratedMatch) -> GrepMatch:
    return GrepMatch(
        path=item.path,
        line_number=item.line_number,
        line=item.line,
        context_before=tuple(item.context_before),
        context_after=tuple(item.context_after),
    )


class _translate_errors:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self, exc_type: object, exc: BaseException | None, tb: object
    ) -> bool:
        if not isinstance(exc, ApiError):
            return False
        match exc.detail:
            case FileNotFoundProblem(detail=detail):
                raise FileNotFoundError(detail) from exc
            case PathOutsideWorkspaceProblem(detail=detail):
                raise PermissionError(detail) from exc
            case (
                InvalidEditProblem(detail=detail)
                | InvalidWorkspaceIdProblem(detail=detail)
                | NotADirectoryProblem(detail=detail)
                | StdinNotSupportedProblem(detail=detail)
            ):
                raise ValueError(detail) from exc
        return False
