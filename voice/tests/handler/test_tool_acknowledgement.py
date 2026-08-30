import asyncio
import wave
from pathlib import Path

import pytest

from voice.events import (
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantToolStarted,
    AudioPlaybackRequested,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded
from voice.handler import ToolAcknowledgementListener
from voice.handler.tool_acknowledgement import TOOL_ACKNOWLEDGEMENTS

_ACKNOWLEDGEMENTS_DIR = Path(__file__).parents[2] / "static" / "acknowledgements"


def _write_acknowledgements(directory: Path) -> dict[str, bytes]:
    acknowledgements = {
        name: f"audio:{name}".encode() for name, _ in TOOL_ACKNOWLEDGEMENTS
    }
    for name, audio in acknowledgements.items():
        (directory / f"{name}.wav").write_bytes(audio)
    return acknowledgements


@pytest.mark.parametrize("name,phrase", TOOL_ACKNOWLEDGEMENTS)
def test_static_acknowledgement_is_16_bit_mono_wav(
    name: str,
    phrase: str,
) -> None:
    path = _ACKNOWLEDGEMENTS_DIR / f"{name}.wav"

    assert phrase
    with wave.open(str(path)) as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 24_000
        assert audio.getnframes() > 0


def test_plays_cached_ack_when_tool_call_follows_silence(
    monkeypatch, tmp_path: Path
) -> None:
    acknowledgements = _write_acknowledgements(tmp_path)

    async def run() -> list[bytes]:
        event_bus = EventBus()
        ToolAcknowledgementListener(
            event_bus=event_bus,
            acknowledgements_dir=tmp_path,
        )
        requested: list[bytes] = []

        async def capture(event: AudioPlaybackRequested) -> None:
            requested.append(event.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)

        await event_bus.dispatch(AssistantResponseStarted(turn_id=3))
        await event_bus.dispatch(AssistantToolStarted(turn_id=3, name="weather"))
        await event_bus.dispatch(AssistantToolStarted(turn_id=3, name="calendar"))
        return requested

    monkeypatch.setattr(
        "voice.handler.tool_acknowledgement.random.choice",
        lambda choices: choices[0],
    )

    assert asyncio.run(run()) == [acknowledgements["on_it"]]


def test_stays_silent_when_assistant_already_spoke(tmp_path: Path) -> None:
    _write_acknowledgements(tmp_path)

    async def run() -> list[bytes]:
        event_bus = EventBus()
        ToolAcknowledgementListener(
            event_bus=event_bus,
            acknowledgements_dir=tmp_path,
        )
        requested: list[bytes] = []

        async def capture(event: AudioPlaybackRequested) -> None:
            requested.append(event.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)

        await event_bus.dispatch(AssistantResponseStarted(turn_id=4))
        await event_bus.dispatch(AssistantTextChunk(turn_id=4, chunk="I'll check."))
        await event_bus.dispatch(AssistantToolStarted(turn_id=4, name="weather"))
        return requested

    assert asyncio.run(run()) == []


def test_resets_state_and_avoids_repeating_the_last_ack(
    monkeypatch, tmp_path: Path
) -> None:
    acknowledgements = _write_acknowledgements(tmp_path)

    async def run() -> list[bytes]:
        event_bus = EventBus()
        ToolAcknowledgementListener(
            event_bus=event_bus,
            acknowledgements_dir=tmp_path,
        )
        requested: list[bytes] = []

        async def capture(event: AudioPlaybackRequested) -> None:
            requested.append(event.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)

        for turn_id in (5, 6):
            await event_bus.dispatch(AssistantResponseStarted(turn_id=turn_id))
            await event_bus.dispatch(
                AssistantToolStarted(turn_id=turn_id, name="weather")
            )
            await event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))
        return requested

    monkeypatch.setattr(
        "voice.handler.tool_acknowledgement.random.choice",
        lambda choices: choices[0],
    )

    assert asyncio.run(run()) == [
        acknowledgements["on_it"],
        acknowledgements["let_me_check"],
    ]
