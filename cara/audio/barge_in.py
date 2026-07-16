import asyncio
from typing import Self

from cara.audio.ports import SpeechRecorder


class BargeInCapture:
    """Owns the background microphone capture for one assistant response."""

    def __init__(self, recorder: SpeechRecorder) -> None:
        self._recorder = recorder
        self._interrupt = asyncio.Event()
        self._cancel = asyncio.Event()
        self._recording: asyncio.Task[bytes | None] | None = None

    @property
    def interrupt(self) -> asyncio.Event:
        return self._interrupt

    async def __aenter__(self) -> Self:
        if self._recording is not None:
            raise RuntimeError("Barge-in capture is already running.")
        self._recording = asyncio.create_task(
            self._recorder.record_until_silence(
                speech_started=self._interrupt,
                cancel=self._cancel,
            )
        )
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._cancel.set()
        if self._recording is not None:
            await self._recording

    async def receive(self) -> bytes | None:
        if self._recording is None:
            raise RuntimeError("Barge-in capture has not been started.")
        return await self._recording
