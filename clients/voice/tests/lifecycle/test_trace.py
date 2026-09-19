import asyncio
import logging
from uuid import UUID

from voice.lifecycle import AssistantToolStarted
from voice.lifecycle.trace import LifecycleTrace

_TURN = UUID("12345678-1234-5678-1234-567812345678")


def test_traces_events_with_short_turn_ids(caplog) -> None:
    event = AssistantToolStarted(turn_id=_TURN, name="lights")

    with caplog.at_level(logging.DEBUG, logger="voice.lifecycle.trace"):
        asyncio.run(LifecycleTrace().on_lifecycle_event(event))

    assert caplog.messages == ["AssistantToolStarted(turn_id=12345678, name='lights')"]
