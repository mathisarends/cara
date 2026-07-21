import asyncio

import pytest

from cara.audio import AudioPlayer


class RecordingOutput:
    def __init__(self) -> None:
        self.audio: list[bytes] = []

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self.audio.append(audio)


def test_audio_player_delegates_to_the_active_output() -> None:
    async def run() -> tuple[RecordingOutput, RecordingOutput]:
        local = RecordingOutput()
        sonos = RecordingOutput()
        player = AudioPlayer({"local": local, "sonos": sonos})

        await player.play(b"local")
        player.set_output("sonos")
        await player.play(b"remote")

        return local, sonos

    local, sonos = asyncio.run(run())

    assert local.audio == [b"local"]
    assert sonos.audio == [b"remote"]


def test_audio_player_reports_available_outputs_for_an_unknown_name() -> None:
    player = AudioPlayer({"local": RecordingOutput(), "sonos": RecordingOutput()})

    with pytest.raises(ValueError, match="Available outputs: local, sonos"):
        player.set_output("kitchen")


def test_audio_player_can_register_and_activate_an_output() -> None:
    player = AudioPlayer({"local": RecordingOutput()})

    player.register_output("sonos", RecordingOutput(), activate=True)

    assert player.active_output == "sonos"
    assert player.available_outputs == ("local", "sonos")
