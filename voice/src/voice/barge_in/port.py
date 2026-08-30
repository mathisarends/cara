import asyncio
import contextlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from voice.audio.models import AudioFormat
from voice.echo_cancellation import EchoPresence
from voice.events.bus import EventBus


@dataclass(frozen=True, slots=True)
class BargeInSignal:
    """Marks the captured audio position at which the user took the floor."""

    sequence: int


@dataclass(frozen=True, slots=True)
class BargeInContext:
    """The session a strategy observes to detect interruptions."""

    event_bus: EventBus
    audio_format: AudioFormat
    echo_presence: EchoPresence


class BargeInStrategy(ABC):
    """Detects that the user takes the floor while the assistant holds it."""

    @abstractmethod
    def set_context(self, context: BargeInContext) -> None:
        """Bind to the session.

        The voice channel calls this while wiring itself up, so a strategy is
        constructed like any other collaborator and learns about the session
        afterwards.
        """

    @abstractmethod
    def signals(self) -> AsyncIterator[BargeInSignal]:
        """Yield one signal per interruption for as long as the session runs."""


class PendingSignal:
    """Holds the one interruption a strategy has detected but not handed over."""

    def __init__(self) -> None:
        self._signals: asyncio.Queue[BargeInSignal] = asyncio.Queue(maxsize=1)

    def put(self, sequence: int) -> None:
        # A pending signal already interrupts the same turn, so drop repeats.
        with contextlib.suppress(asyncio.QueueFull):
            self._signals.put_nowait(BargeInSignal(sequence=sequence))

    async def stream(self) -> AsyncIterator[BargeInSignal]:
        while True:
            yield await self._signals.get()
