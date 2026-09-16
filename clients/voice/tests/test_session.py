import asyncio
from contextlib import AsyncExitStack
from typing import cast

from voice import VoiceChannel, VoiceSession


class _Channel:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


def test_session_owns_channel_and_external_resource_lifecycle() -> None:
    async def scenario() -> tuple[_Channel, bool]:
        channel = _Channel()
        resources = AsyncExitStack()
        await resources.__aenter__()
        resource_closed = False

        async def close_resource() -> None:
            nonlocal resource_closed
            resource_closed = True

        resources.push_async_callback(close_resource)
        session = VoiceSession(
            channel=cast(VoiceChannel, channel),
            resources=resources,
        )

        async with session:
            await session.run()

        await session.close()
        return channel, resource_closed

    channel, resource_closed = asyncio.run(scenario())

    assert channel.started
    assert channel.stopped
    assert resource_closed
