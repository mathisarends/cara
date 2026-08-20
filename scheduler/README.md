# scheduler

`scheduler` is a small, in-memory async scheduler. It is independent of agent
runtimes, web frameworks, persistence layers, and payload domains.

The package provides three triggers:

```python
Trigger = At | Interval | Cron
```

Payloads are generic and remain strongly typed from registration through
execution. The host application owns their meaning:

```python
from dataclasses import dataclass
from datetime import timedelta

from scheduler import ScheduledRun, Scheduler


@dataclass(frozen=True, slots=True)
class AgentWork:
    agent_id: str
    prompt: str


async def run_agent(run: ScheduledRun[AgentWork]) -> None:
    work = run.payload
    await agent_runtime.run(agent_id=work.agent_id, prompt=work.prompt)


scheduler = Scheduler[AgentWork](run_agent)
scheduler.interval(
    every=timedelta(minutes=30),
    payload=AgentWork(
        agent_id="cara",
        prompt="Run your heartbeat.",
    ),
    name="heartbeat",
)
```

The scheduler itself only sees an opaque `AgentWork` value. A different host
can use `Scheduler[Email]`, `Scheduler[Command]`, or any other concrete type
without changing the library.

## API

`Scheduler.schedule()` accepts an `At`, `Interval`, or `Cron` trigger directly.
The convenience methods mirror those trigger types:

```python
scheduler.at(when, payload=payload)
scheduler.interval(every=timedelta(minutes=5), payload=payload)
scheduler.cron(
    expression="0 7 * * 1-5",
    timezone="Europe/Berlin",
    payload=payload,
)
```

All methods return `ScheduledJob[PayloadT]`. The execution callback receives a
`ScheduledRun[PayloadT]` containing the job ID, trigger kind, intended execution
time, name, and the same typed payload.

## Examples

- [`examples/quickstart.py`](examples/quickstart.py) is a short, executable demo
  with an interval and a one-shot `At` job.
- [`examples/long_running.py`](examples/long_running.py) demonstrates how an
  agent-specific payload and adapter stay in the host application.

Run the quickstart from the workspace root:

```shell
uv run --package scheduler python scheduler/examples/quickstart.py
```

## Behavior

- `At` runs once at a timezone-aware `datetime`. Overdue jobs run as soon as
  the scheduler starts.
- `Interval` repeats at a fixed interval. Its first run happens immediately by
  default; pass `run_immediately=False` to wait for one interval.
- `Cron` uses a standard five-field expression and an IANA timezone.
- Different jobs may run concurrently. A single recurring job never overlaps
  with itself, and missed occurrences are skipped rather than replayed.
- A failed run is logged and does not stop later recurring runs.
- Jobs live in memory. A host can restore definitions from its own persistence
  layer before starting the scheduler.
