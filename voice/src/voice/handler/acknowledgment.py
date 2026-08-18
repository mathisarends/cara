import random
from collections.abc import Sequence

from voice.acknowledgment import GENERIC_ACKNOWLEDGMENTS, AcknowledgmentStrategy
from voice.events import UserSpeechEnded
from voice.events.bus import EventBus


class AcknowledgmentHandler:
    """Fills the gap between the end of user speech and the assistant's answer."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        strategy: AcknowledgmentStrategy,
        phrases: Sequence[str] = GENERIC_ACKNOWLEDGMENTS,
    ) -> None:
        unique_phrases = dict.fromkeys(phrases)
        if len(unique_phrases) < 2:
            raise ValueError("phrases must hold at least two distinct phrases")
        self._strategy = strategy
        self._phrases = tuple(unique_phrases)
        self._last_phrase: str | None = None

        event_bus.on(UserSpeechEnded, self._on_user_speech_ended)

    async def _on_user_speech_ended(self, _: UserSpeechEnded) -> None:
        await self._strategy.acknowledge(self._next_phrase())

    def _next_phrase(self) -> str:
        # Two distinct phrases are guaranteed, so excluding the last one always
        # leaves a candidate and no repeat can slip through.
        candidates = [phrase for phrase in self._phrases if phrase != self._last_phrase]
        self._last_phrase = random.choice(candidates)
        return self._last_phrase
