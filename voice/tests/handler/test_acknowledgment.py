import asyncio

import pytest

from voice.acknowledgment import (
    GENERIC_ACKNOWLEDGMENTS,
    AcknowledgmentStrategy,
    NoAcknowledgment,
)
from voice.events import UserSpeechEnded
from voice.events.bus import EventBus
from voice.handler import AcknowledgmentHandler


class _RecordingAcknowledgment(AcknowledgmentStrategy):
    def __init__(self) -> None:
        super().__init__()
        self.phrases: list[str] = []

    async def acknowledge(self, phrase: str) -> None:
        self.phrases.append(phrase)


def _acknowledge(utterances: int, **kwargs: object) -> list[str]:
    async def run() -> list[str]:
        bus = EventBus()
        strategy = _RecordingAcknowledgment()
        AcknowledgmentHandler(event_bus=bus, strategy=strategy, **kwargs)
        for _ in range(utterances):
            await bus.dispatch(UserSpeechEnded())
        return strategy.phrases

    return asyncio.run(run())


def test_acknowledges_generic_phrase_when_user_stops_speaking() -> None:
    phrases = _acknowledge(1)

    assert len(phrases) == 1
    assert phrases[0] in GENERIC_ACKNOWLEDGMENTS


def test_acknowledges_every_utterance_without_repeating_itself() -> None:
    phrases = _acknowledge(4, phrases=("one", "two"))

    assert phrases in (["one", "two", "one", "two"], ["two", "one", "two", "one"])


def test_never_repeats_a_phrase_back_to_back() -> None:
    phrases = _acknowledge(50)

    assert all(
        earlier != later for earlier, later in zip(phrases, phrases[1:], strict=False)
    )


@pytest.mark.parametrize("phrases", [(), ("only",), ("same", "same")])
def test_rejects_a_pool_that_cannot_avoid_repeating(phrases: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        AcknowledgmentHandler(
            event_bus=EventBus(), strategy=NoAcknowledgment(), phrases=phrases
        )
