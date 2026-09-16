import asyncio
import wave
from pathlib import Path
from uuid import uuid4

import pytest

from voice.acknowledgement import (
    TOOL_ACKNOWLEDGEMENTS,
    ToolAcknowledgementIntegration,
)
from voice.events import (
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantToolStarted,
    AudioPlaybackRequested,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded
from voice.integration import VoiceIntegrationBridge

_ACKNOWLEDGEMENTS_DIR = Path(__file__).parents[1] / "static" / "acknowledgements"


def _write_acknowledgements(directory: Path) -> dict[str, bytes]:
    acknowledgements = {
        name: f"audio:{name}".encode() for name, _ in TOOL_ACKNOWLEDGEMENTS
    }
    for name, audio in acknowledgements.items():
        (directory / f"{name}.wav").write_bytes(audio)
    return acknowledgements


async def _prepare_integration(event_bus: EventBus, directory: Path) -> None:
    integration = ToolAcknowledgementIntegration(acknowledgements_dir=directory)
    bridge = VoiceIntegrationBridge(event_bus=event_bus, integrations=(integration,))
    bridge.setup()
    await bridge.prepare()


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
        requested: list[bytes] = []

        async def capture(event: AudioPlaybackRequested) -> None:
            requested.append(event.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)
        await _prepare_integration(event_bus, tmp_path)

        turn_id = uuid4()
        await event_bus.emit(AssistantResponseStarted(turn_id=turn_id))
        await event_bus.emit(AssistantToolStarted(turn_id=turn_id, name="weather"))
        await event_bus.emit(AssistantToolStarted(turn_id=turn_id, name="calendar"))
        return requested

    monkeypatch.setattr(
        "voice.acknowledgement.random.choice",
        lambda choices: choices[0],
    )

    assert asyncio.run(run()) == [acknowledgements["on_it"]]


def test_stays_silent_when_assistant_already_spoke(tmp_path: Path) -> None:
    _write_acknowledgements(tmp_path)

    async def run() -> list[bytes]:
        event_bus = EventBus()
        requested: list[bytes] = []

        async def capture(event: AudioPlaybackRequested) -> None:
            requested.append(event.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)
        await _prepare_integration(event_bus, tmp_path)

        turn_id = uuid4()
        await event_bus.emit(AssistantResponseStarted(turn_id=turn_id))
        await event_bus.emit(AssistantTextChunk(turn_id=turn_id, chunk="I'll check."))
        await event_bus.emit(AssistantToolStarted(turn_id=turn_id, name="weather"))
        return requested

    assert asyncio.run(run()) == []


def test_resets_state_and_avoids_repeating_the_last_ack(
    monkeypatch, tmp_path: Path
) -> None:
    acknowledgements = _write_acknowledgements(tmp_path)

    async def run() -> list[bytes]:
        event_bus = EventBus()
        requested: list[bytes] = []

        async def capture(event: AudioPlaybackRequested) -> None:
            requested.append(event.audio)

        event_bus.on_request(AudioPlaybackRequested, capture)
        await _prepare_integration(event_bus, tmp_path)

        for turn_id in (uuid4(), uuid4()):
            await event_bus.emit(AssistantResponseStarted(turn_id=turn_id))
            await event_bus.emit(AssistantToolStarted(turn_id=turn_id, name="weather"))
            await event_bus.emit(VoiceTurnEnded(turn_id=turn_id))
        return requested

    monkeypatch.setattr(
        "voice.acknowledgement.random.choice",
        lambda choices: choices[0],
    )

    assert asyncio.run(run()) == [
        acknowledgements["on_it"],
        acknowledgements["let_me_check"],
    ]
