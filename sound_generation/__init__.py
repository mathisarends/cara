from .ports import SoundGenerator
from .views import SoundEffectFormat, SoundEffectRequest, SoundEffectResponse

__all__ = [
    "ElevenLabsSoundGenerator",
    "SoundEffectFormat",
    "SoundEffectRequest",
    "SoundEffectResponse",
    "SoundGenerator",
]


def __getattr__(name: str) -> object:
    if name == "ElevenLabsSoundGenerator":
        from .generator import ElevenLabsSoundGenerator

        return ElevenLabsSoundGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
