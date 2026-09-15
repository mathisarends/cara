from sandbox_manager.features.sandbox.application import ExecCommand, ExecOutcome
from sandbox_manager.features.sandbox.presentation.schemas import (
    ExecRequest,
    ExecResponse,
    SandboxResponse,
)


def to_exec_command(request: ExecRequest) -> ExecCommand:
    return ExecCommand(
        argv=request.argv,
        cwd=request.cwd,
        env=request.env,
        stdin=request.stdin.encode() if request.stdin is not None else None,
        timeout_seconds=request.timeout_seconds,
    )


def to_exec_response(outcome: ExecOutcome) -> ExecResponse:
    return ExecResponse(
        exit_code=outcome.exit_code,
        stdout=outcome.stdout.decode(errors="replace"),
        stderr=outcome.stderr.decode(errors="replace"),
        timed_out=outcome.timed_out,
    )


def to_sandbox_response(workspace_id: str, sandbox_id: str) -> SandboxResponse:
    return SandboxResponse(workspace_id=workspace_id, sandbox_id=sandbox_id)
