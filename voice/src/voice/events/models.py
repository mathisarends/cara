from transitbus import Event


class WakeWordDetected(Event):
    """Emitted when the configured wake word is detected."""

    score: float
    sequence: int
    name: str


class VoiceTurnTimedOut(Event):
    turn_id: int


class VoiceTurnFailed(Event):
    turn_id: int
    message: str
