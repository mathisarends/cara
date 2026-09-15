# scheduler

Small, in-memory async scheduler, independent of agent runtimes, web
frameworks, persistence layers, and payload domains. Three triggers (`At`,
`Interval`, `Cron`); payloads are generic and stay strongly typed from
registration through execution — the host owns their meaning.

```python
scheduler = Scheduler(run_agent)
scheduler.schedule("heartbeat", trigger=Interval(timedelta(minutes=30)), payload=AgentWork(...))
await scheduler.start()
```

- `JobRunner[PayloadT]` — translates a due `ScheduledRun` into host behavior.
  Each run carries `next_run_at` (`None` on the final run).
- The scheduler keeps no persistence. Hosts store `next_run_at` themselves and
  resume after a restart with `schedule(..., next_run_at=...)`;
  `first_run(trigger, now)` computes the initial run without arming a job.

At-least-once delivery: a run in progress when the process exits is
redelivered after restart if the host only persists `next_run_at` afterwards.

## Dependencies

`croniter`. Used by [`gateway-server`](../../gateway) to run automations
persisted in the gateway database.
