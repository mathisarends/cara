import asyncio
import logging
from collections.abc import Iterable, Sequence

from voice.activation.port import (
    Activation,
    ActivationSource,
    ListenActivation,
)
from voice.events import SessionEnded, SessionStarted
from voice.events.bus import EventBus
from voice.events.models import (
    Request,
    VoiceTurnEnded,
    VoiceTurnRequested,
    VoiceTurnStarted,
)

logger = logging.getLogger(__name__)


class ActivationCoordinator:
    """Starts a voice turn from any activation source while the session is idle."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        sources: Iterable[ActivationSource],
    ) -> None:
        self._event_bus = event_bus
        self._sources = tuple(sources)
        if not self._sources:
            raise ValueError("A voice session needs at least one activation source.")
        self._session_active = False
        self._turn_active = False

        event_bus.on(SessionStarted, self._on_session_started)
        event_bus.on(SessionEnded, self._on_session_ended)
        event_bus.on(VoiceTurnStarted, self._on_voice_turn_started)
        event_bus.on(VoiceTurnEnded, self._on_voice_turn_ended)

    async def run(self) -> None:
        """Pump every source until the first one stops producing activations.

        A source whose stream ends has lost whatever it listens on — a closed
        microphone, in the wake word's case — so the session ends with it.
        """
        tasks = [
            asyncio.create_task(
                self._pump(source),
                name=f"voice-activation-{type(source).__name__}",
            )
            for source in self._sources
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            await _cancel(tasks)
        for task in done:
            task.result()

    @property
    def _can_start_turn(self) -> bool:
        return self._session_active and not self._turn_active

    async def _on_session_started(self, _: SessionStarted) -> None:
        self._session_active = True
        self._turn_active = False

    async def _on_session_ended(self, _: SessionEnded) -> None:
        self._session_active = False

    async def _on_voice_turn_started(self, _: VoiceTurnStarted) -> None:
        self._turn_active = True

    async def _on_voice_turn_ended(self, _: VoiceTurnEnded) -> None:
        self._turn_active = False

    async def _pump(self, source: ActivationSource) -> None:
        async for activation in source.activations():
            if not self._can_start_turn:
                logger.debug(
                    "Ignoring activation from %s while the session cannot start a turn",
                    type(source).__name__,
                )
                continue
            await self._event_bus.request(_turn_request_for(activation))


def _turn_request_for(activation: Activation) -> Request:
    match activation:
        case ListenActivation():
            return VoiceTurnRequested(
                sequence=activation.sequence,
                speech_start_timeout=activation.speech_start_timeout,
                activation=activation.kind,
            )


async def _cancel(tasks: Sequence[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
