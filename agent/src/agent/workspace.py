import os
from pathlib import Path


def resolve_workspace_root(
    configured_root: Path | None = None,
    *,
    relative_to: Path | None = None,
) -> Path:
    environment_root = os.environ.get("CARA_WORKSPACE_ROOT")
    selected_root = (
        Path(environment_root)
        if environment_root
        else configured_root or Path.home() / ".cara" / "workspace"
    )
    expanded_root = selected_root.expanduser()
    if expanded_root.is_absolute():
        return expanded_root.resolve()
    return ((relative_to or Path.cwd()) / expanded_root).resolve()
