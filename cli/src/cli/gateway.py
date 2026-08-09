import subprocess
import sys
from enum import Enum
from pathlib import Path

import psutil

_PROCESS_MARKER = "gateway.main:app"


class GatewayState(Enum):
    RUNNING = "running"
    STOPPED = "stopped"


def project_root() -> Path:
    root = Path(__file__).resolve().parents[3]
    if not (root / "gateway" / "pyproject.toml").is_file():
        raise RuntimeError(f"Cara project root not found at {root}")
    return root


def state_root() -> Path:
    return Path.home() / ".cara"


def start() -> tuple[int, bool]:
    if _gateway_process() is not None:
        return 0, False

    root = project_root()
    migration = subprocess.run(
        [_project_executable("gateway-migrate")],
        cwd=root,
        check=False,
    )
    if migration.returncode:
        return migration.returncode, False

    config_root = state_root()
    config_root.mkdir(parents=True, exist_ok=True)
    with (config_root / "gateway.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [_project_executable("uvicorn"), _PROCESS_MARKER],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **_detached_process_options(),
        )
    (config_root / "gateway.pid").write_text(str(process.pid), encoding="ascii")
    return 0, True


def stop() -> tuple[int, bool]:
    process = _gateway_process()
    if process is None:
        return 0, False

    processes = process.children(recursive=True)
    processes.append(process)
    for running_process in processes:
        running_process.terminate()
    _, alive = psutil.wait_procs(processes, timeout=5)
    for running_process in alive:
        running_process.kill()
    psutil.wait_procs(alive, timeout=5)
    _remove_pid_file()
    return 0, True


def status() -> GatewayState:
    if _gateway_process() is None:
        return GatewayState.STOPPED
    return GatewayState.RUNNING


def _project_executable(name: str) -> str:
    scripts_directory = "Scripts" if sys.platform == "win32" else "bin"
    suffix = ".exe" if sys.platform == "win32" else ""
    executable = project_root() / ".venv" / scripts_directory / f"{name}{suffix}"
    if not executable.is_file():
        raise RuntimeError(
            f"{name} is not installed in the project environment; run `uv sync`."
        )
    return str(executable)


def _gateway_process() -> psutil.Process | None:
    pid_file = state_root() / "gateway.pid"
    try:
        pid = int(pid_file.read_text(encoding="ascii"))
        process = psutil.Process(pid)
        command = " ".join(process.cmdline())
    except (FileNotFoundError, ValueError, psutil.Error):
        _remove_pid_file()
        return None
    if _PROCESS_MARKER not in command:
        _remove_pid_file()
        return None
    return process


def _remove_pid_file() -> None:
    (state_root() / "gateway.pid").unlink(missing_ok=True)


def _detached_process_options() -> dict[str, object]:
    if sys.platform == "win32":
        return {
            "creationflags": (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        }
    return {"start_new_session": True}
