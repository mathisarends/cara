import pytest
from pydantic import ValidationError

from scheduler import CronSchedule, JobDefinition

EXAMPLE_JOB = {
    "id": "00000000-0000-0000-0000-000000000123",
    "name": "Freitagszusammenfassung",
    "schedule": {
        "kind": "cron",
        "expression": "0 18 * * 5",
        "timezone": "Europe/Berlin",
    },
    "payload": {
        "kind": "agent_prompt",
        "prompt": "Fasse zusammen, was ich diese Woche gemacht habe.",
    },
}


def test_parses_agent_job_declaration() -> None:
    job = JobDefinition.model_validate(EXAMPLE_JOB)

    assert isinstance(job.schedule, CronSchedule)
    assert job.schedule.expression == "0 18 * * 5"
    assert job.payload["prompt"].startswith("Fasse zusammen")
    assert job.model_dump(mode="json", exclude_none=True) == {
        **EXAMPLE_JOB,
        "enabled": True,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [("expression", "not cron"), ("timezone", "Mars/Olympus_Mons")],
)
def test_rejects_invalid_cron_schedule(field: str, value: str) -> None:
    schedule = {"kind": "cron", "expression": "0 18 * * 5", "timezone": "Europe/Berlin"}
    schedule[field] = value

    with pytest.raises(ValidationError):
        JobDefinition.model_validate({**EXAMPLE_JOB, "schedule": schedule})


def test_rejects_unknown_declaration_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        JobDefinition.model_validate({**EXAMPLE_JOB, "python_callable": "tasks.run"})
