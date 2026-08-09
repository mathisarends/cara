from pathlib import Path
from subprocess import CompletedProcess

from cli import gateway


class _StartedProcess:
    pid = 1234


class _RunningProcess:
    def __init__(self, children=()) -> None:
        self._children = list(children)
        self.terminated = False
        self.killed = False

    def children(self, *, recursive: bool):
        assert recursive
        return self._children

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def test_start_runs_migration_then_detached_uvicorn(
    tmp_path: Path, monkeypatch
) -> None:
    commands: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(gateway, "state_root", lambda: tmp_path)
    monkeypatch.setattr(gateway, "project_root", lambda: Path("project"))
    monkeypatch.setattr(gateway, "_gateway_process", lambda: None)
    monkeypatch.setattr(
        gateway, "_project_executable", lambda name: f"environment/{name}"
    )
    monkeypatch.setattr(gateway, "_detached_process_options", lambda: {})

    def run(command: list[str], **options) -> CompletedProcess:
        commands.append(("run", command))
        return CompletedProcess(command, 0)

    def popen(command: list[str], **options) -> _StartedProcess:
        commands.append(("popen", command))
        return _StartedProcess()

    monkeypatch.setattr(gateway.subprocess, "run", run)
    monkeypatch.setattr(gateway.subprocess, "Popen", popen)

    assert gateway.start() == (0, True)
    assert commands == [
        ("run", ["environment/gateway-migrate"]),
        ("popen", ["environment/uvicorn", "gateway.main:app"]),
    ]
    assert (tmp_path / "gateway.pid").read_text(encoding="ascii") == "1234"
    assert (tmp_path / "gateway.log").is_file()


def test_start_does_nothing_when_gateway_is_running(monkeypatch) -> None:
    monkeypatch.setattr(gateway, "_gateway_process", _RunningProcess)

    assert gateway.start() == (0, False)


def test_status_reports_managed_process_state(monkeypatch) -> None:
    monkeypatch.setattr(gateway, "_gateway_process", lambda: _RunningProcess())
    assert gateway.status() is gateway.GatewayState.RUNNING

    monkeypatch.setattr(gateway, "_gateway_process", lambda: None)
    assert gateway.status() is gateway.GatewayState.STOPPED


def test_stop_terminates_gateway_process_tree(tmp_path: Path, monkeypatch) -> None:
    child = _RunningProcess()
    process = _RunningProcess([child])
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_text("1234", encoding="ascii")
    monkeypatch.setattr(gateway, "state_root", lambda: tmp_path)
    monkeypatch.setattr(gateway, "_gateway_process", lambda: process)
    monkeypatch.setattr(
        gateway.psutil,
        "wait_procs",
        lambda processes, timeout: (processes, []),
    )

    assert gateway.stop() == (0, True)
    assert child.terminated
    assert process.terminated
    assert not pid_file.exists()
