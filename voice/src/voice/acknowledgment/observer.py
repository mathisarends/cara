import logging
import random
from collections.abc import Sequence

from voice.acknowledgment.phrases import GENERIC_ACKNOWLEDGMENTS
from voice.acknowledgment.port import AcknowledgmentContext, AcknowledgmentStrategy
from voice.observer import Observer, ObserverContext

logger = logging.getLogger(__name__)


class AcknowledgmentObserver(Observer):
    """Fills the gap between the end of user speech and the assistant's answer."""

    def __init__(
        self,
        *,
        strategy: AcknowledgmentStrategy,
        phrases: Sequence[str] = GENERIC_ACKNOWLEDGMENTS,
    ) -> None:
        unique_phrases = dict.fromkeys(phrases)
        if len(unique_phrases) < 2:
            raise ValueError("phrases must hold at least two distinct phrases")
        self._strategy = strategy
        self._phrases = tuple(unique_phrases)
        self._last_phrase: str | None = None

    async def prepare(self, context: ObserverContext) -> None:
        self._strategy.set_context(
            AcknowledgmentContext(audio_player=context.audio_player)
        )

    async def on_user_stopped_speaking(self) -> None:
        phrase = self._next_phrase()
        logger.info("Acknowledgment: %s", phrase)
        await self._strategy.acknowledge(phrase)

    def _next_phrase(self) -> str:
        # Two distinct phrases are guaranteed, so excluding the last one always
        # leaves a candidate and no repeat can slip through.
        candidates = [phrase for phrase in self._phrases if phrase != self._last_phrase]
        self._last_phrase = random.choice(candidates)
        return self._last_phrase
