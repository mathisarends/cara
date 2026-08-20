# scheduler

`scheduler` is a small, in-memory async scheduler for kicking off agents. It is
independent of any particular agent runtime, web framework, or persistence
layer.

```python
import asyncio
from datetime import UTC, datetime, timedelta

from scheduler import AgentRunRequest, Scheduler


async def run_agent(request: AgentRunRequest) -> None:
    await agent_runtime.run(
        agent_id=request.agent_id,
        payload=dict(request.payload),
    )


async def main() -> None:
    scheduler = Scheduler(run_agent)

    scheduler.heartbeat(
        "personal-assistant",
        every=timedelta(minutes=5),
        payload={"prompt": "Check whether anything needs my attention."},
    )
    scheduler.reminder(
        "personal-assistant",
        at=datetime(2026, 8, 21, 9, tzinfo=UTC),
        payload={"prompt": "Remind me to call the dentist."},
    )
    scheduler.cron(
        "daily-planner",
        expression="0 7 * * 1-5",
        timezone="Europe/Berlin",
        payload={"prompt": "Prepare my morning briefing."},
    )

    async with scheduler:
        await asyncio.Event().wait()


asyncio.run(main())
```

The runner is the only integration point. It receives an `AgentRunRequest`
containing the target `agent_id`, the job identity, the intended execution time,
and an immutable payload mapping. Scheduling methods return a `ScheduledJob`, so
the host can retain its generated ID or supply a stable `job_id` itself.

## Examples

- [`examples/quickstart.py`](examples/quickstart.py) is a short, executable demo
  with an immediate heartbeat and a one-shot reminder.
- [`examples/long_running.py`](examples/long_running.py) shows how a service can
  register stable jobs, run until shutdown, and route requests into an agent
  runtime.

Run the quickstart from the workspace root:

```shell
uv run --package scheduler python scheduler/examples/quickstart.py
```

## Behavior

- A heartbeat repeats at a fixed interval. By default its first run happens
  immediately; pass `run_immediately=False` to wait for one interval.
- A reminder runs once at an aware `datetime`. Overdue reminders run as soon as
  the scheduler starts.
- A cron job uses a standard five-field cron expression and an IANA timezone.
- Different jobs may run concurrently. A single recurring job never overlaps
  with itself, and missed occurrences are skipped rather than replayed.
- A failed agent run is logged and does not stop later recurring runs.
- Jobs live in memory. A future host integration can restore definitions from
  its own persistence layer before starting the scheduler.
