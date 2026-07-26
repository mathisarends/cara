from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from cara.file_system import Workspace

_DEFAULT_IMAGE = "cara-bash-sandbox:latest"


@dataclass(frozen=True)
class BashSandboxResult:
    return_code: int
    output: str


@dataclass(frozen=True)
class BashSandboxMount:
    source: Path
    target: str
    read_only: bool = True

    def __post_init__(self) -> None:
        source = self.source.resolve(strict=True)
        target = PurePosixPath(self.target)
        if "," in str(source):
            raise ValueError("Sandbox mount source must not contain a comma")
        if not target.is_absolute() or ".." in target.parts:
            raise ValueError("Sandbox mount target must be an absolute container path")
        if "," in self.target:
            raise ValueError("Sandbox mount target must not contain a comma")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", str(target))


@dataclass(frozen=True)
class BashSandboxConfig:
    image: str = _DEFAULT_IMAGE
    network: str = "none"
    forwarded_environment: tuple[str, ...] = ()
    mounts: tuple[BashSandboxMount, ...] = ()
    allowed_commands: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.image:
            raise ValueError("Docker image must not be empty")
        if not self.network:
            raise ValueError("Docker network must not be empty")
        invalid_environment = [name for name in self.forwarded_environment if not _valid_environment_name(name)]
        if invalid_environment:
            raise ValueError(f"Invalid environment variable names: {', '.join(invalid_environment)}")


@dataclass(frozen=True)
class BashSandboxRequest:
    command: str
    workspace: Workspace
    config: BashSandboxConfig = field(default_factory=BashSandboxConfig)


def _valid_environment_name(name: str) -> bool:
    return (
        bool(name)
        and (name[0].isalpha() or name[0] == "_")
        and all(character.isalnum() or character == "_" for character in name)
    )
