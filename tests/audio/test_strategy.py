import asyncio

import pytest

from cara.audio import AudioOutput, AudioPlayer


class RecordingOutput:
    def __init__(self, output: AudioOutput) -> None:
        self._output = output
        self.audio: list[bytes] = []

    @property
    def output(self) -> AudioOutput:
        return self._output

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        self.audio.append(audio)


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


def test_audio_player_can_register_and_activate_an_output() -> None:
    player = AudioPlayer(RecordingOutput(AudioOutput.LOCAL))

    player.register_output(RecordingOutput(AudioOutput.SONOS), activate=True)

    assert player.active_output is AudioOutput.SONOS
    assert player.available_outputs == (AudioOutput.LOCAL, AudioOutput.SONOS)
