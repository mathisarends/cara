from transitbus import Event


class WakeWordDetected(Event):
    """Emitted when the configured wake word is detected."""

    score: float
