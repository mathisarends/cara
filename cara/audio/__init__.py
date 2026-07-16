from .echo import EchoCancellationSettings, WebRtcEchoCanceller
from .player import WavAudioPlayer
from .ports import AudioPlayer, EchoCanceller, SpeechRecorder
from .recorder import MicrophoneInputSettings, MicrophoneRecorder

__all__ = [
    "AudioPlayer",
    "EchoCancellationSettings",
    "EchoCanceller",
    "MicrophoneRecorder",
    "MicrophoneInputSettings",
    "SpeechRecorder",
    "WebRtcEchoCanceller",
    "SonosAudioPlayer",
    "WavAudioPlayer",
]


def __getattr__(name: str) -> object:
    if name == "SonosAudioPlayer":
        from .sonos import SonosAudioPlayer

        return SonosAudioPlayer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
