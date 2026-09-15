import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

import httpx
from agenttoolkit.builtins import CommandResult
from agenttoolkit.builtins.fs import Entry, GrepMatch
from agenttoolkit.builtins.shell import DEFAULT_TIMEOUT, CommandTimeout
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr


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
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._root = root
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=str(settings.url).rstrip("/"),
            headers={"Authorization": f"Bearer {settings.token.get_secret_value()}"},
        )

    @property
    def root(self) -> Path:
        return self._root

    async def ensure(self) -> None:
        response = await self._client.put(f"{self._base}/sandbox")
        _raise_for_status(response)

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
        response = await self._client.post(
            f"{self._base}/exec",
            json={
                "argv": ["/bin/bash", "-lc", command],
                "cwd": _container_cwd(cwd),
                "env": env or {},
                "stdin": stdin.decode() if isinstance(stdin, bytes) else stdin,
                "timeout_seconds": timeout_seconds,
            },
            timeout=timeout_seconds + 5,
        )
        _raise_for_status(response)
        result = response.json()
        return CommandResult(
            command=command,
            returncode=result["exit_code"],
            stdout=result["stdout"],
            stderr=result["stderr"],
            duration_seconds=time.perf_counter() - started,
            timed_out=result.get("timed_out", False),
        )

    async def read_file(self, path: str | Path, *, encoding: str | None = None) -> str:
        _require_utf8(encoding)
        response = await self._client.get(f"{self._base}/files/{_path(path)}")
        _raise_for_status(response)
        return response.text

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
        response = await self._client.put(
            f"{self._base}/files/{_path(path)}",
            json={"content": content},
        )
        _raise_for_status(response)

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
        response = await self._client.post(
            f"{self._base}/edit/{_path(path)}",
            json={"old": old, "new": new, "replace_all": replace_all},
        )
        _raise_for_status(response)
        return response.json()["count"]

    async def list_dir(
        self,
        path: str | Path = ".",
        *,
        recursive: bool = False,
        limit: int | None = None,
    ) -> list[Entry]:
        response = await self._client.get(
            f"{self._base}/entries",
            params={"path": str(path), "recursive": recursive},
        )
        _raise_for_status(response)
        entries = [Entry(**item) for item in response.json()]
        return entries if limit is None else entries[:limit]

    async def glob(self, pattern: str) -> list[Entry]:
        response = await self._client.get(
            f"{self._base}/glob", params={"pattern": pattern}
        )
        _raise_for_status(response)
        return [Entry(**item) for item in response.json()]

    async def grep(
        self,
        pattern: str,
        *,
        glob: str | None = None,
        case_sensitive: bool = True,
        context_lines: int = 0,
        max_matches: int | None = None,
    ) -> list[GrepMatch]:
        response = await self._client.post(
            f"{self._base}/grep",
            json={
                "pattern": pattern,
                "glob": glob,
                "case_sensitive": case_sensitive,
                "context_lines": context_lines,
                "max_matches": max_matches,
            },
        )
        _raise_for_status(response)
        return [GrepMatch(**item) for item in response.json()]

    async def stat(self, path: str | Path) -> Entry | None:
        response = await self._client.get(
            f"{self._base}/stat", params={"path": str(path)}
        )
        _raise_for_status(response)
        value = response.json()
        return None if value is None else Entry(**value)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def _base(self) -> str:
        return f"/v1/workspaces/{quote(self._settings.workspace_id, safe='')}"


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


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == 404:
        raise FileNotFoundError(response.request.url.path)
    if response.status_code == 403:
        raise PermissionError(response.text)
    if response.status_code == 400:
        raise ValueError(response.text)
    response.raise_for_status()
