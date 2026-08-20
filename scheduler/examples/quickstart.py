import asyncio
from datetime import timedelta

from scheduler import AgentRunRequest, Scheduler


async def run_agent(request: AgentRunRequest) -> None:
    prompt = request.payload["prompt"]
    print(f"[{request.kind}] {request.agent_id}: {prompt}")


async def main() -> None:
    scheduler = Scheduler(run_agent)

    heartbeat = scheduler.heartbeat(
        "demo-agent",
        every=timedelta(seconds=1),
        payload={"prompt": "Look for unfinished work."},
        name="demo heartbeat",
    )
    scheduler.reminder(
        "demo-agent",
        after=timedelta(seconds=2),
        payload={"prompt": "This reminder only runs once."},
        name="demo reminder",
    )

    print(f"registered heartbeat {heartbeat.id}")
    async with scheduler:
        await asyncio.sleep(3.2)


if __name__ == "__main__":
    asyncio.run(main())
