from .player import WavAudioPlayer
from .ports import AudioPlayer, SpeechRecorder
from .recorder import MicrophoneInputSettings, MicrophoneRecorder

__all__ = [
    "AudioPlayer",
    "MicrophoneRecorder",
    "MicrophoneInputSettings",
    "SpeechRecorder",
    "SonosAudioPlayer",
    "WavAudioPlayer",
]


def __getattr__(name: str) -> object:
    if name == "SonosAudioPlayer":
        from .sonos import SonosAudioPlayer

        return SonosAudioPlayer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
