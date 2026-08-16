import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Protocol, Self

from transitbus import EventBus

from agent.events import (
    AssistantInterrupted,
    SessionEnded,
    SessionStarted,
    UserTurnStarted,
)
from voice.audio.output import Earcon, EarconPlayer
from voice.barge_in import BargeIn
from voice.sound_listener import SoundListener
from voice.speech import SpeechInput, SpeechOutput
from voice.wakeword.ports import WakeWordSessionSource

logger = logging.getLogger(__name__)

DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS = 7.0


class _TextResponder(Protocol):
    async def respond(
        self,
        text: str,
        *,
        on_interim_response: Callable[[str], Awaitable[None]] | None = None,
    ) -> str: ...


class _ResponseInterrupted(Exception):
    pass


class _BargeInMonitor:
    def __init__(self, detector: BargeIn) -> None:
        self._detector = detector
        self._interrupt = asyncio.Event()
        self._cancel = asyncio.Event()
        self._listening: asyncio.Task[None] | None = None

    @property
    def interrupt(self) -> asyncio.Event:
        return self._interrupt

    async def __aenter__(self) -> Self:
        self._listening = asyncio.create_task(self._listen())
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._cancel.set()
        if self._listening is not None:
            await self._listening

    async def _listen(self) -> None:
        await self._detector.wait(cancel=self._cancel)
        if not self._cancel.is_set():
            self._interrupt.set()


class VoiceSession:
    """Coordinates wake-word-driven conversations over speech input and output."""

    def __init__(
        self,
        *,
        agent: _TextResponder,
        speech_input: SpeechInput,
        speech_output: SpeechOutput,
        wake_word_listener: WakeWordSessionSource,
        barge_in: BargeIn,
        event_bus: EventBus,
        earcons: EarconPlayer,
        follow_up_timeout_seconds: float = DEFAULT_FOLLOW_UP_TIMEOUT_SECONDS,
    ) -> None:
        self._agent = agent
        self._speech_input = speech_input
        self._speech_output = speech_output
        self._wake_word_listener = wake_word_listener
        self._barge_in = barge_in
        self._event_bus = event_bus
        self._earcons = earcons
        self._follow_up_timeout_seconds = follow_up_timeout_seconds
        self._sound_listener = SoundListener(self._event_bus, self._earcons)

    async def run(self) -> None:
        """Wait for wake words and run one voice conversation after each detection."""
        async for _ in self._wake_word_listener.detections():
            await self.run_once()

    async def run_once(self) -> None:
        """Run one active, potentially multi-turn voice conversation."""
        follow_up = False
        pending_transcript: str | None = None
        ready: threading.Event | None = threading.Event()
        await self._event_bus.dispatch(SessionStarted())
        wake_earcon = asyncio.create_task(self._announce_wake(ready))
        try:
            while True:
                if pending_transcript is not None:
                    transcript = pending_transcript
                    pending_transcript = None
                else:
                    transcript = await self._receive(follow_up=follow_up, ready=ready)
                    ready = None
                if transcript is None:
                    break
                if not transcript:
                    logger.info("Ignoring empty transcription")
                    break

                async with _BargeInMonitor(self._barge_in) as barge_in:
                    try:
                        answer = await _respond_until_interrupted(
                            self._agent,
                            transcript,
                            interrupt=barge_in.interrupt,
                            on_interim_response=lambda interim: (
                                self._speech_output.send(
                                    interim,
                                    cancel=barge_in.interrupt,
                                )
                            ),
                        )
                    except _ResponseInterrupted:
                        pending_transcript = await self._receive_barge_in()
                        if pending_transcript is None:
                            break
                        follow_up = False
                        continue
                    if barge_in.interrupt.is_set():
                        pending_transcript = await self._receive_barge_in()
                        if pending_transcript is None:
                            break
                        follow_up = False
                        continue
                    if answer:
                        await self._speech_output.send(
                            answer, cancel=barge_in.interrupt
                        )
                if barge_in.interrupt.is_set():
                    pending_transcript = await self._receive_barge_in()
                    if pending_transcript is None:
                        break
                    follow_up = False
                    continue
                follow_up = True
        finally:
            wake_earcon.cancel()
            await asyncio.gather(wake_earcon, return_exceptions=True)
            await self._event_bus.dispatch(SessionEnded())

    async def _announce_wake(self, ready: threading.Event) -> None:
        try:
            await self._earcons.play(Earcon.WAKE)
        finally:
            ready.set()

    async def _receive_barge_in(self) -> str | None:
        await self._event_bus.dispatch(AssistantInterrupted())
        await self._event_bus.dispatch(UserTurnStarted())
        return await self._speech_input.receive()

    async def _receive(
        self,
        *,
        follow_up: bool = False,
        ready: threading.Event | None = None,
    ) -> str | None:
        await self._event_bus.dispatch(UserTurnStarted())
        initial_silence_timeout = self._follow_up_timeout_seconds if follow_up else None
        return await self._speech_input.receive(
            initial_silence_timeout=initial_silence_timeout,
            ready=ready,
        )


async def _respond_until_interrupted(
    agent: _TextResponder,
    text: str,
    *,
    interrupt: asyncio.Event,
    on_interim_response: Callable[[str], Awaitable[None]],
) -> str:
    response_task = asyncio.create_task(
        agent.respond(text, on_interim_response=on_interim_response)
    )
    interrupt_task = asyncio.create_task(interrupt.wait())
    try:
        done, _ = await asyncio.wait(
            {response_task, interrupt_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if interrupt_task in done and interrupt.is_set():
            raise _ResponseInterrupted
        return await response_task
    finally:
        for task in (response_task, interrupt_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(response_task, interrupt_task, return_exceptions=True)
