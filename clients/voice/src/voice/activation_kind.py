from enum import StrEnum


class ActivationKind(StrEnum):
    WAKE_WORD = "wake_word"
    MANUAL = "manual"
    FOLLOW_UP = "follow_up"
    BARGE_IN = "barge_in"
