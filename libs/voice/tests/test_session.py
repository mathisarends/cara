import asyncio
from contextlib import AsyncExitStack

import pytest
from doubles import (
    FakeVoiceBackend,
    RecordingAudioOutput,
    StreamingAudioInput,
    settle,
)

from voice import VoiceSession
from voice.audio import BufferedAudioInput
from voice.runtime import VoiceRuntime


class _Resources:
    def __init__(self) -> None:
        self.stack = AsyncExitStack()
        self.close_calls = 0
        self.stack.push_async_callback(self._close)

    async def _close(self) -> None:
        self.close_calls += 1


def _session(resources: _Resources) -> tuple[VoiceSession, StreamingAudioInput]:
    microphone = StreamingAudioInput()
    runtime = VoiceRuntime(
        backend=FakeVoiceBackend(),
        audio_input=BufferedAudioInput(microphone),
        audio_output=RecordingAudioOutput(),
    )
    return VoiceSession(runtime=runtime, resources=resources.stack), microphone


def test_close_stops_the_runtime_and_resources_exactly_once() -> None:
    resources = _Resources()

    async def scenario() -> StreamingAudioInput:
        session, microphone = _session(resources)
        async with session:
            run = asyncio.create_task(session.run())
            await settle()
            await session.close()
            await asyncio.wait_for(run, timeout=1)
        await session.close()
        return microphone

    microphone = asyncio.run(scenario())

    assert microphone.stop_calls == 1
    assert resources.close_calls == 1


def test_a_closed_session_cannot_run() -> None:
    resources = _Resources()

    async def scenario() -> None:
        session, _ = _session(resources)
        await session.close()
        with pytest.raises(RuntimeError, match="closed"):
            await session.run()

    asyncio.run(scenario())

    assert resources.close_calls == 1
