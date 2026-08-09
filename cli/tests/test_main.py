from pathlib import Path

from typer.testing import CliRunner

from cli import main

runner = CliRunner()


def test_onboard_reports_created_and_existing_paths(monkeypatch) -> None:
    soul = Path("workspace/SOUL.md")
    skills = soul.parent / "skills"
    monkeypatch.setattr(
        main,
        "onboard",
        lambda: [(soul, True), (skills, False)],
    )

    result = runner.invoke(main.app, ["onboard"])

    assert result.exit_code == 0
    assert f"Created {soul}" in result.stdout
    assert f"Already exists {skills}" in result.stdout
    assert "Cara is ready." in result.stdout


def test_gateway_command_is_dispatched(monkeypatch) -> None:
    called = False

    def status() -> main.gateway.GatewayState:
        nonlocal called
        called = True
        return main.gateway.GatewayState.STOPPED

    monkeypatch.setattr(main.gateway, "status", status)

    result = runner.invoke(main.app, ["gateway", "status"])

    assert result.exit_code == 0
    assert called
    assert "Gateway is stopped." in result.stdout


def test_gateway_failure_becomes_cli_exit_code(monkeypatch) -> None:
    monkeypatch.setattr(main.gateway, "start", lambda: (7, False))

    result = runner.invoke(main.app, ["gateway", "start"])

    assert result.exit_code == 7
    assert "Gateway command failed" in result.stderr
