import os
from pathlib import Path


def resolve_workspace_root(configured_root: Path | None = None) -> Path:
    environment_root = os.environ.get("CARA_WORKSPACE_ROOT")
    selected_root = (
        Path(environment_root)
        if environment_root
        else configured_root or Path.home() / ".cara" / "workspace"
    )
    return selected_root.expanduser().resolve()
