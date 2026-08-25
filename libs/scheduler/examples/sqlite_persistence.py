import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scheduler import ScheduledRun, Scheduler, SqliteJobStore


@dataclass(frozen=True, slots=True)
class Message:
    text: str


class MessageCodec:
    def encode(self, value: Message) -> str:
        return json.dumps(asdict(value))

    def decode(self, value: str) -> Message:
        return Message(**json.loads(value))


async def handle(run: ScheduledRun[Message]) -> None:
    print(f"[{run.scheduled_for.isoformat()}] {run.payload.text}")


async def main() -> None:
    store = SqliteJobStore(
        Path("scheduler.db"),
        payload_codec=MessageCodec(),
    )
    scheduler = Scheduler(handle, store)

    # A stable ID lets startup reconcile configuration without adding duplicates.
    if await store.get("weekday-report") is None:
        await scheduler.cron(
            expression="0 8 * * 1-5",
            timezone="Europe/Berlin",
            payload=Message("Prepare the weekday report."),
            job_id="weekday-report",
            name="weekday report",
        )

    async with scheduler:
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
