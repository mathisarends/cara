import asyncio
from datetime import timedelta

from scheduler import AgentRunRequest, Scheduler


class AgentRuntime:
    async def run(self, agent_id: str, payload: dict[str, object]) -> None:
        print(f"Starting {agent_id} with {payload}")


async def serve(runtime: AgentRuntime, shutdown: asyncio.Event) -> None:
    async def run_agent(request: AgentRunRequest) -> None:
        await runtime.run(request.agent_id, dict(request.payload))

    scheduler = Scheduler(run_agent)

    # Stable IDs make definitions easy to reconcile with persisted host config.
    scheduler.heartbeat(
        "primary-agent",
        every=timedelta(minutes=5),
        run_immediately=False,
        payload={"prompt": "Check inboxes and surface anything urgent."},
        job_id="primary-agent-heartbeat",
    )
    scheduler.cron(
        "morning-briefing-agent",
        expression="0 7 * * 1-5",
        timezone="Europe/Berlin",
        payload={"prompt": "Prepare the weekday morning briefing."},
        job_id="weekday-morning-briefing",
    )

    async with scheduler:
        await shutdown.wait()


async def main() -> None:
    shutdown = asyncio.Event()
    try:
        await serve(AgentRuntime(), shutdown)
    finally:
        shutdown.set()


if __name__ == "__main__":
    asyncio.run(main())
