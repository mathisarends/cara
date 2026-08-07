# Scheduler

The scheduler stores agent-authored job declarations in SQLite and fires them
inside the process that owns it. The gateway supplies a `JobRunner` that knows
how to execute the payload, create the requested session, and deliver its
result. No Python callable is stored in a job.

```json
{
  "id": "job-123",
  "name": "Freitagszusammenfassung",
  "schedule": {
    "kind": "cron",
    "expression": "0 18 * * 5",
    "timezone": "Europe/Berlin"
  },
  "payload": {
    "kind": "agent_prompt",
    "prompt": "Fasse zusammen, was ich diese Woche gemacht habe."
  },
  "session": {
    "mode": "isolated"
  },
  "delivery": {
    "kind": "chat",
    "channel": "telegram"
  }
}
```

Validate agent input with `JobDefinition.model_validate(data)`, then register
it with `await scheduler.add(job)`. The async management API also provides
`get`, `list`, `remove`, `enable`, `disable`, and `run_now`.

Supported schedules are:

- `{"kind": "at", "at": "2026-08-06T18:00:00+02:00"}` for one run
- `{"kind": "every", "seconds": 600}` for a fixed interval
- `{"kind": "cron", "expression": "0 18 * * 5", "timezone": "Europe/Berlin"}`

One-shot jobs are deleted after a successful run. Recurring schedules remain
stored until explicitly removed.

## Runnable example

Run `uv run python scheduler/examples/smoke_test.py` from the repository root
for a short smoke test. It registers a job that runs every second, prints three
executions, lists the persisted job, and removes it again. The example uses a
temporary SQLite database, so it does not leave any state behind.
