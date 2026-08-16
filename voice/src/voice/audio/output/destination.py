from enum import StrEnum

from voice.audio.output.port import AudioOutput


class AudioDestination(StrEnum):
    LOCAL = "local"
    SONOS = "sonos"


class RoutedAudioOutput(AudioOutput):
    """An audio output addressable by the playback router."""

    @property
    def destination(self) -> AudioDestination:
        raise NotImplementedError
