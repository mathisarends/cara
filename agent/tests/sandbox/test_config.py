from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError

from agent.sandbox import SandboxDefinition, create_sandbox


def _definition(**overrides: object) -> SandboxDefinition:
    return SandboxDefinition.model_validate(
        {
            "image": "example:latest",
            "shell": "/bin/sh",
            "defaults": {
                "home": "/tmp",
                "timeout_seconds": 5,
                "max_output_bytes": 1024,
            },
            "limits": {"memory_bytes": 1024, "pids": 8, "cpus": 1},
            **overrides,
        }
    )


def test_project_sandbox_definition(project_sandbox: SandboxDefinition) -> None:
    assert project_sandbox.image == "cara-bash-sandbox:latest"
    assert project_sandbox.shell == PurePosixPath("/bin/bash")
    assert project_sandbox.defaults.home == PurePosixPath("/tmp")
    assert project_sandbox.defaults.timeout_seconds == 15
    assert project_sandbox.defaults.max_output_bytes == 1_000_000
    assert project_sandbox.limits.memory_bytes == 512 * 1024 * 1024
    assert project_sandbox.limits.pids == 512
    assert project_sandbox.limits.cpus == 1
    assert project_sandbox.mounts.paths == ()
    assert project_sandbox.reserved_targets == {PurePosixPath("/workspace")}


def test_create_sandbox_uses_definition(
    project_sandbox: SandboxDefinition, tmp_path: Path
) -> None:
    sandbox = create_sandbox(tmp_path, project_sandbox)

    open_argv = sandbox.build_open_argv(container_name="test")
    assert open_argv[-4] == project_sandbox.image
    assert open_argv[-3] == str(project_sandbox.shell)
    assert sandbox.defaults.environment["HOME"] == str(project_sandbox.defaults.home)
    assert sandbox.defaults.limits.timeout_seconds == 15
    assert sandbox.defaults.limits.max_output_bytes == 1_000_000
    assert sandbox.policy.limits.memory_bytes == 512 * 1024 * 1024
    assert sandbox.policy.limits.pids == 512
    assert sandbox.policy.limits.cpus == 1
    assert sandbox.policy.enable_network_access == project_sandbox.network_access


def test_configured_path_mounts_resolve_relative_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "notes"
    source.mkdir()
    monkeypatch.chdir(tmp_path)
    definition = _definition(
        mounts={"paths": [{"source": "notes", "target": "/notes"}]}
    )

    sandbox = create_sandbox(tmp_path, definition)

    mount = sandbox.mounts[-1]
    assert mount.source == source.resolve()
    assert mount.target == PurePosixPath("/notes")
    assert not mount.writable


def test_missing_path_mount_source_is_rejected(tmp_path: Path) -> None:
    definition = _definition(
        mounts={"paths": [{"source": str(tmp_path / "missing"), "target": "/missing"}]}
    )

    with pytest.raises(ValueError, match="mount source does not exist"):
        create_sandbox(tmp_path, definition)


def test_definition_rejects_configured_reserved_mount() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        _definition(
            mounts={"cli_credentials": [{"name": "example", "target": "/workspace"}]},
            reserved_targets=["/workspace"],
        )
