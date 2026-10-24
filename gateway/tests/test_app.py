from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from gateway.features.alarm.infrastructure import AlarmRuntime
from gateway.features.automation.infrastructure import AutomationRuntime


@pytest.fixture
def shutdown_trace(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[str]]:
    shutdown: list[str] = []
    stop_alarms = AlarmRuntime.stop
    stop_automations = AutomationRuntime.stop

    async def record_alarm_stop(alarm_runtime: AlarmRuntime) -> None:
        await stop_alarms(alarm_runtime)
        shutdown.append("alarms")

    async def record_automation_stop(automation_runtime: AutomationRuntime) -> None:
        await stop_automations(automation_runtime)
        shutdown.append("automations")

    def record_engine_disposal(_engine: Engine) -> None:
        shutdown.append("database")

    monkeypatch.setattr(AlarmRuntime, "stop", record_alarm_stop)
    monkeypatch.setattr(AutomationRuntime, "stop", record_automation_stop)

    event.listen(Engine, "engine_disposed", record_engine_disposal)
    try:
        yield shutdown
    finally:
        event.remove(Engine, "engine_disposed", record_engine_disposal)


def test_background_runtimes_stop_before_the_database_is_disposed(
    app: FastAPI,
    shutdown_trace: list[str],
) -> None:
    with TestClient(app):
        pass

    assert shutdown_trace == ["alarms", "automations", "database"]


def test_partial_startup_stops_started_runtimes_before_disposing_the_database(
    app: FastAPI,
    shutdown_trace: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start_alarms = AlarmRuntime.start

    async def fail_after_start(alarm_runtime: AlarmRuntime) -> None:
        await start_alarms(alarm_runtime)
        raise RuntimeError("Alarm startup aborted")

    monkeypatch.setattr(AlarmRuntime, "start", fail_after_start)

    with pytest.raises(RuntimeError, match="Alarm startup aborted"), TestClient(app):
        pass

    assert shutdown_trace == ["alarms", "automations", "database"]
