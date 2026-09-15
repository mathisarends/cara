from pydantic import BaseModel, ConfigDict, Field


class ExecRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    argv: tuple[str, ...] = Field(min_length=1)
    cwd: str = "/workspace"
    env: dict[str, str] = Field(default_factory=dict)
    stdin: str | None = None
    timeout_seconds: float = Field(default=15, gt=0, le=3600)


class ExecResponse(BaseModel):
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


class FileWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


class FileEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old: str
    new: str
    replace_all: bool = False


class GrepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str
    glob: str | None = None
    case_sensitive: bool = True
    context_lines: int = Field(default=0, ge=0, le=10)
    max_matches: int | None = Field(default=None, ge=1)


class SandboxResponse(BaseModel):
    workspace_id: str
    container_id: str
