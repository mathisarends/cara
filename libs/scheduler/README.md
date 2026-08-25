# scheduler

Small, in-memory async scheduler, independent of agent runtimes, web
frameworks, persistence layers, and payload domains. Three triggers (`At`,
`Interval`, `Cron`); payloads are generic and stay strongly typed from
registration through execution — the host owns their meaning.

```python
scheduler = Scheduler(run_agent, MemoryJobStore[AgentWork]())
await scheduler.interval(every=timedelta(minutes=30), payload=AgentWork(...), name="heartbeat")
```

- `JobStore[PayloadT]` — async add/update/remove/get/list. `MemoryJobStore`
  for tests/ephemeral processes; `SqliteJobStore` (with a host-provided
  `Codec`) for restart persistence.
- `JobRunner[PayloadT]` — translates a due `ScheduledRun` into host behavior.

At-least-once delivery: a run in progress when the process exits may be
redelivered after restart. V1 does not lease jobs across processes, so
multiple schedulers against one database can double-run a job.

## Dependencies

None beyond the standard library for `MemoryJobStore`; `SqliteJobStore` needs
a host-supplied payload `Codec`. Used by [`gateway-server`](../../gateway/server)
for periodic housekeeping via `SchedulerProvider`.
