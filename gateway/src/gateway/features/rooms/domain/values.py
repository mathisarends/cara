from enum import StrEnum


class Capability(StrEnum):
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    MEDIA_PLAYBACK = "media_playback"
    LIGHT = "light"


class RoomFunction(StrEnum):
    CONVERSATION = "conversation"
    ANNOUNCE = "announce"
    MUSIC = "music"
    LIGHT = "light"


class DeviceKind(StrEnum):
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    LIGHT = "light"


class DeviceStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class RoomState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
