from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError

from agent.sandbox import (
    SandboxDefinition,
    create_sandbox,
    load_sandbox_definition,
)


def test_load_default_sandbox_definition() -> None:
    definition = load_sandbox_definition()

    assert definition.image == "cara-bash-sandbox:latest"
    assert definition.shell == PurePosixPath("/bin/bash")
    assert definition.resolve_workspace_root() == Path.cwd()
    assert definition.workspace.max_file_bytes is None
    assert definition.defaults.home == PurePosixPath("/tmp")
    assert definition.defaults.timeout_seconds == 15
    assert definition.defaults.max_output_bytes == 1_000_000
    assert definition.limits.memory_bytes == 256 * 1024 * 1024
    assert definition.limits.pids == 64
    assert definition.limits.cpus == 1
    assert definition.reserved_targets == {PurePosixPath("/workspace")}


def test_create_sandbox_uses_definition(tmp_path: Path) -> None:
    definition = load_sandbox_definition()

    sandbox = create_sandbox(tmp_path, definition=definition)

    open_argv = sandbox.build_open_argv(container_name="test")
    assert open_argv[-4] == definition.image
    assert open_argv[-3] == str(definition.shell)
    assert sandbox.defaults.environment["HOME"] == str(definition.defaults.home)
    assert sandbox.defaults.limits.timeout_seconds == 15
    assert sandbox.defaults.limits.max_output_bytes == 1_000_000
    assert sandbox.policy.limits.memory_bytes == 256 * 1024 * 1024
    assert sandbox.policy.limits.pids == 64
    assert sandbox.policy.limits.cpus == 1
    assert sandbox.policy.enable_network_access == definition.network_access


def test_definition_resolves_workspace_relative_to_yml(tmp_path: Path) -> None:
    config_path = tmp_path / "sandbox.yml"
    config_path.write_text(
        """\
image: example:latest
shell: /bin/sh
workspace:
  root: work
  max_file_bytes: 4096
defaults:
  home: /tmp
  timeout_seconds: 1
  max_output_bytes: 100
limits:
  memory_bytes: 1024
  pids: 2
  cpus: 0.5
""",
        encoding="utf-8",
    )

    definition = SandboxDefinition.from_yaml(config_path)

    assert definition.resolve_workspace_root() == tmp_path / "work"
    assert definition.workspace.max_file_bytes == 4096


def test_definition_rejects_configured_reserved_mount() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        SandboxDefinition.model_validate(
            {
                "image": "example:latest",
                "shell": "/bin/sh",
                "defaults": {
                    "home": "/tmp",
                    "timeout_seconds": 1,
                    "max_output_bytes": 100,
                },
                "limits": {"memory_bytes": 1024, "pids": 2, "cpus": 1},
                "mounts": {
                    "cli_credentials": [{"name": "example", "target": "/workspace"}]
                },
                "reserved_targets": ["/workspace"],
            }
        )
