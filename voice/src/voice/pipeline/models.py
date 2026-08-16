from enum import StrEnum


class TurnState(StrEnum):
    STARTING = "starting"
    ARMED = "armed"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
