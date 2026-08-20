import asyncio
from dataclasses import dataclass
from datetime import timedelta

from scheduler import MemoryJobStore, ScheduledRun, Scheduler


@dataclass(frozen=True, slots=True)
class AgentWork:
    agent_id: str
    prompt: str


class AgentRuntime:
    async def run(self, agent_id: str, prompt: str) -> None:
        print(f"Starting {agent_id}: {prompt}")


async def serve(runtime: AgentRuntime, shutdown: asyncio.Event) -> None:
    async def run_agent(run: ScheduledRun[AgentWork]) -> None:
        work = run.payload
        await runtime.run(work.agent_id, work.prompt)

    scheduler = Scheduler(run_agent, MemoryJobStore[AgentWork]())

    # Agent-specific concepts live in this host-side adapter, not in scheduler.
    await scheduler.interval(
        every=timedelta(minutes=5),
        run_immediately=False,
        payload=AgentWork(
            agent_id="cara",
            prompt="Run your heartbeat.",
        ),
        job_id="cara-heartbeat",
        name="heartbeat",
    )
    await scheduler.cron(
        expression="0 7 * * 1-5",
        timezone="Europe/Berlin",
        payload=AgentWork(
            agent_id="cara",
            prompt="Prepare the weekday morning briefing.",
        ),
        job_id="weekday-morning-briefing",
    )

    async with scheduler:
        await shutdown.wait()


async def main() -> None:
    await serve(AgentRuntime(), asyncio.Event())


if __name__ == "__main__":
    asyncio.run(main())
