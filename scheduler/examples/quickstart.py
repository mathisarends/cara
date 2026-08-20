import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from scheduler import MemoryJobStore, ScheduledRun, Scheduler


@dataclass(frozen=True, slots=True)
class Message:
    text: str


async def handle(run: ScheduledRun[Message]) -> None:
    print(f"[{run.kind}] {run.payload.text}")


async def main() -> None:
    scheduler = Scheduler(handle, MemoryJobStore[Message]())

    interval = await scheduler.interval(
        every=timedelta(seconds=1),
        payload=Message("Look for unfinished work."),
        name="demo interval",
    )
    await scheduler.at(
        datetime.now(UTC) + timedelta(seconds=2),
        payload=Message("This job only runs once."),
        name="demo one-shot",
    )

    print(f"registered interval {interval.id}")
    async with scheduler:
        await asyncio.sleep(3.2)


if __name__ == "__main__":
    asyncio.run(main())
