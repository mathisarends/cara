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


class SandboxResponse(BaseModel):
    workspace_id: str
    sandbox_id: str
