from .earcons import Earcon, EarconPlayer
from .echo import EchoCancellationSettings, WebRtcEchoCanceller
from .player import WavAudioPlayer
from .ports import AudioPlayer, EchoCanceller, SpeechRecorder
from .recorder import MicrophoneInputSettings, MicrophoneRecorder

__all__ = [
    "AudioPlayer",
    "EchoCancellationSettings",
    "EchoCanceller",
    "Earcon",
    "EarconPlayer",
    "MicrophoneRecorder",
    "MicrophoneInputSettings",
    "SpeechRecorder",
    "WebRtcEchoCanceller",
    "SonosAudioPlayer",
    "SonosSettings",
    "WavAudioPlayer",
]


def __getattr__(name: str) -> object:
    if name in ("SonosAudioPlayer", "SonosSettings"):
        from . import sonos

        return getattr(sonos, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
