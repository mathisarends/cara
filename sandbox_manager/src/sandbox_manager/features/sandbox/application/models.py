from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecCommand:
    argv: tuple[str, ...]
    cwd: str
    env: Mapping[str, str]
    stdin: bytes | None
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class ExecOutcome:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
