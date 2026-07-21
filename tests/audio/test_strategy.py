import asyncio

import pytest

from cara.audio import AudioOutput, AudioPlayer


class RecordingOutput:
    def __init__(self, output: AudioOutput) -> None:
        self._output = output
        self.audio: list[bytes] = []
        self.volume = 1.0

    @property
    def output(self) -> AudioOutput:
        return self._output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self.audio.append(audio)

    async def get_volume(self) -> float:
        return self.volume

    async def set_volume(self, volume: float) -> None:
        self.volume = volume


def test_audio_player_delegates_to_the_active_output() -> None:
    async def run() -> tuple[RecordingOutput, RecordingOutput]:
        local = RecordingOutput(AudioOutput.LOCAL)
        sonos = RecordingOutput(AudioOutput.SONOS)
        player = AudioPlayer(local, sonos)

        await player.play(b"local")
        player.set_output(AudioOutput.SONOS)
        await player.play(b"remote")

        return local, sonos

    local, sonos = asyncio.run(run())

    assert local.audio == [b"local"]
    assert sonos.audio == [b"remote"]


def test_audio_player_reports_when_an_output_is_not_configured() -> None:
    player = AudioPlayer(RecordingOutput(AudioOutput.LOCAL))

    with pytest.raises(ValueError, match="Available outputs: local"):
        player.set_output(AudioOutput.SONOS)


def test_audio_player_delegates_volume_control_to_the_active_output() -> None:
    async def run() -> tuple[float, float]:
        local = RecordingOutput(AudioOutput.LOCAL)
        sonos = RecordingOutput(AudioOutput.SONOS)
        player = AudioPlayer(local, sonos)

        await player.set_volume(0.3)
        player.set_output(AudioOutput.SONOS)
        await player.set_volume(0.8)

        return local.volume, await player.get_volume()

    local_volume, sonos_volume = asyncio.run(run())

    assert local_volume == 0.3
    assert sonos_volume == 0.8


def test_audio_player_can_register_and_activate_an_output() -> None:
    player = AudioPlayer(RecordingOutput(AudioOutput.LOCAL))

    player.register_output(RecordingOutput(AudioOutput.SONOS), activate=True)

    assert player.active_output is AudioOutput.SONOS
    assert player.available_outputs == (AudioOutput.LOCAL, AudioOutput.SONOS)
